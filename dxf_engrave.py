import ezdxf
import sys
import argparse
from shapely.geometry import Polygon, LineString
from shapely.validation import make_valid

def process_dxf(input_path, output_path, step):
    try:
        doc = ezdxf.readfile(input_path)
    except Exception as e:
        print(f"Error: Could not read file {input_path}. {e}")
        return

    msp = doc.modelspace()
    all_polygons = []

    for entity in msp.query('LWPOLYLINE'):
        points = [p[:2] for p in entity.get_points()]
        if len(points) >= 3:
            poly = make_valid(Polygon(points))
            if poly.geom_type == 'Polygon':
                all_polygons.append(poly)
            elif hasattr(poly, 'geoms'):
                for p in poly.geoms:
                    if p.geom_type == 'Polygon':
                        all_polygons.append(p)

    if not all_polygons:
        print("No valid contours found.")
        return

    all_polygons.sort(key=lambda p: p.area, reverse=True)
    combined = all_polygons[0]
    for poly in all_polygons[1:]:
        combined = combined.symmetric_difference(poly)

    minx, miny, maxx, maxy = combined.bounds
    new_doc = ezdxf.new()
    new_msp = new_doc.modelspace()

    # Исходные контуры
    for poly in all_polygons:
        new_msp.add_lwpolyline(list(poly.exterior.coords), dxfattribs={'color': 5})

    # Генерация линий
    y = miny + step
    while y < maxy:
        line = LineString([(minx - 5, y), (maxx + 5, y)])
        inter = line.intersection(combined)
        if not inter.is_empty:
            if hasattr(inter, 'geoms'):
                for g in inter.geoms:
                    new_msp.add_line(g.coords[0], g.coords[-1], dxfattribs={'color': 2})
            else:
                new_msp.add_line(inter.coords[0], inter.coords[-1], dxfattribs={'color': 2})
        y += step

    new_doc.saveas(output_path)
    print(f"Success! Saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InoxHatch Pro - DXF Engraving Tool")
    parser.add_argument("input", help="Input DXF file path")
    parser.add_argument("--step", type=float, default=1.0, help="Hatch step in mm (default: 1.0)")
    args = parser.parse_args()
    
    out_name = args.input.replace(".dxf", "_hatch.dxf")
    process_dxf(args.input, out_name, args.step)
