import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from shapely.geometry import Polygon, mapping

try:
    import rasterio
    from rasterio.windows import Window
    from rasterio.features import shapes
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False

class SatelliteImageProcessor:
    """
    Handles large satellite scenes (~10,000 x 10,000 pixels) via windowed tiling,
    feeds tiles through the CNN segmentation pipeline, and vectorizes detected raster pixels 
    into clean GeoJSON coordinate polygons for map rendering.
    """

    def __init__(self, tile_size: int = 512, overlap: int = 64):
        self.tile_size = tile_size
        self.overlap = overlap
        self.stride = tile_size - overlap

    def generate_tiles_from_array(self, image_array: np.ndarray) -> List[Tuple[np.ndarray, int, int]]:
        """
        Slices a large numpy image matrix into overlapping 512x512 CNN-ready tiles.
        Returns list of (tile_data, row_offset, col_offset).
        """
        # Assume shape is (Channels, Height, Width)
        c, h, w = image_array.shape
        tiles = []
        
        for y in range(0, max(1, h - self.tile_size + 1), self.stride):
            for x in range(0, max(1, w - self.tile_size + 1), self.stride):
                y_end = min(y + self.tile_size, h)
                x_end = min(x + self.tile_size, w)
                
                # Extract tile and pad with zeros if edge tile is smaller than tile_size
                tile_patch = np.zeros((c, self.tile_size, self.tile_size), dtype=image_array.dtype)
                extracted_slice = image_array[:, y:y_end, x:x_end]
                tile_patch[:, :extracted_slice.shape[1], :extracted_slice.shape[2]] = extracted_slice
                
                tiles.append((tile_patch, y, x))
                
        return tiles

    def vectorize_segmentation_mask(
        self, 
        binary_mask: np.ndarray, 
        transform: Optional[Any] = None,
        min_pixel_area: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Converts raster pixel mask arrays outputted by the CNN into scalable GeoJSON polygons.
        If a Rasterio GeoTransform is supplied, automatically converts pixels directly into Lat/Long degrees.
        """
        geojsons = []
        
        if not RASTERIO_AVAILABLE or transform is None:
            # Fallback approximate conversion for mock testing when raw geotiff metadata isn't supplied
            # Bounding box around non-zero pixels
            y_indices, x_indices = np.where(binary_mask > 0)
            if len(y_indices) >= min_pixel_area:
                min_x, max_x = int(np.min(x_indices)), int(np.max(x_indices))
                min_y, max_y = int(np.min(y_indices)), int(np.max(y_indices))
                
                poly = Polygon([
                    [min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y], [min_x, min_y]
                ])
                geojsons.append({"type": "Feature", "geometry": mapping(poly), "properties": {"class_id": 1}})
            return geojsons

        # Exact GIS geometric transformation via rasterio.features.shapes
        # Converts pixel grid clusters directly to geospatial coordinate vectors
        mask_uint8 = binary_mask.astype(np.uint8)
        polygon_generator = shapes(mask_uint8, mask=mask_uint8 > 0, transform=transform)
        
        for geometry_dict, value in polygon_generator:
            poly = Polygon(geometry_dict["coordinates"][0])
            if poly.area >= min_pixel_area:  # Filter out tiny digital noise spikes
                geojsons.append({
                    "type": "Feature", 
                    "geometry": geometry_dict, 
                    "properties": {"class_id": int(value)}
                })

        return geojsons
