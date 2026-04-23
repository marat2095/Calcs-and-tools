import sys
import argparse
import math
import ezdxf
from ezdxf import path
from shapely.geometry import Polygon, LineString
from shapely.ops import linemerge
from shapely.validation import make_valid

def process_dxf(input_path, output_path, step):
    try:
        doc = ezdxf.readfile(input_path)
    except Exception as e:
        print(f"Ошибка при чтении файла {input_path}. {e}")
        return

    msp = doc.modelspace()
    lines_soup = []

    # 1. СОБИРАЕМ ЛЮБЫЕ ФИГУРЫ И ПРЕВРАЩАЕМ ИХ В ОТРЕЗКИ
    supported_types = {'LWPOLYLINE', 'POLYLINE', 'LINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'SPLINE'}
    
    for entity in msp:
        if entity.dxftype() in supported_types:
            try:
                p = path.make_path(entity)
                # Разбиваем плавные кривые на микро-отрезки (идеально для ЧПУ)
                vertices = list(p.flattening(distance=0.01))
                if len(vertices) > 1:
                    lines_soup.append(LineString(vertices))
            except Exception:
                continue

    if not lines_soup:
        print("Подходящая геометрия не найдена.")
        return

    # 2. УМНАЯ СШИВКА (Аналог _JOIN в AutoCAD)
    # Соединяем разрозненные отрезки, если их концы совпадают
    merged = linemerge(lines_soup)
    
    if merged.geom_type in ['LineString', 'LinearRing']:
        merged_list = [merged]
    elif merged.geom_type == 'MultiLineString':
        merged_list = merged.geoms
    else:
        merged_list = []

    all_valid_polygons = []
    
    # 3. СОЗДАЕМ ПОЛИГОНЫ ТОЛЬКО ИЗ ЗАМКНУТЫХ КОНТУРОВ
    for line in merged_list:
        coords = list(line.coords)
        if len(coords) >= 3:
            # Проверяем, замкнут ли контур (допуск 0.1 мм на микро-разрывы)
            dist = math.hypot(coords[0][0] - coords[-1][0], coords[0][1] - coords[-1][1])
            is_closed = dist < 0.1
            
            if is_closed:
                # Если есть микро-разрыв, принудительно замыкаем
                if dist > 0:
                    coords[-1] = coords[0]
                    line = LineString(coords)
                
                try:
                    poly = make_valid(Polygon(line))
                    if poly.geom_type == 'Polygon' and not poly.is_empty:
                        all_valid_polygons.append(poly)
                    elif hasattr(poly, 'geoms'):
                        for geom in poly.geoms:
                            if geom.geom_type == 'Polygon':
                                all_valid_polygons.append(geom)
                except Exception:
                    continue

    if not all_valid_polygons:
        print("Замкнутые контуры не найдены. Убедитесь, что линии пересекаются без разрывов.")
        return

    # 4. ВЫРЕЗАНИЕ ОТВЕРСТИЙ (Вложенность XOR)
    # Сортируем от больших к малым, чтобы дырки правильно вырезались
    all_valid_polygons.sort(key=lambda p: p.area, reverse=True)
    combined = all_valid_polygons[0]
    for poly in all_valid_polygons[1:]:
        combined = combined.symmetric_difference(poly)

    minx, miny, maxx, maxy = combined.bounds
    
    # 5. СОЗДАЕМ НОВЫЙ ЧЕРТЕЖ
    new_doc = ezdxf.new()
    new_msp = new_doc.modelspace()

    # Исходные границы (синим цветом для контроля)
    for poly in all_valid_polygons:
        new_msp.add_lwpolyline(list(poly.exterior.coords), dxfattribs={'color': 5})

    # 6. ГЕНЕРАЦИЯ ШТРИХОВКИ
    y = miny + step
    print(f"Генерация штриховки (шаг {step} мм)...")
    
    while y < maxy:
        line = LineString([(minx - 10, y), (maxx + 10, y)])
        try:
            inter = line.intersection(combined)
            if not inter.is_empty:
                if hasattr(inter, 'geoms'):
                    for g in inter.geoms:
                        if g.geom_type == 'LineString':
                            new_msp.add_line(g.coords[0], g.coords[-1], dxfattribs={'color': 2})
                elif inter.geom_type == 'LineString':
                    new_msp.add_line(inter.coords[0], inter.coords[-1], dxfattribs={'color': 2})
        except Exception:
            pass
        y += step

    new_doc.saveas(output_path)
    print(f"Готово! Результат сохранен в: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InoxHatch Pro - Генератор гравировки DXF")
    parser.add_argument("input", help="Путь к исходному файлу DXF")
    parser.add_argument("--step", type=float, default=1.0, help="Шаг штриховки в мм (по умолчанию: 1.0)")
    args = parser.parse_args()
    
    out_name = args.input.replace(".dxf", "_hatch.dxf")
    process_dxf(args.input, out_name, args.step)
