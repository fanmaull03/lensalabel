"""Tests for EasyOCR reading-order normalization."""

from app.ocr.reader import sort_reading_order


def box(x: int, y: int, width: int = 40, height: int = 10) -> list[list[int]]:
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


def test_sort_reading_order_single_column():
    detections = [
        (box(55, 100), "kata dua", 0.9),
        (box(10, 100), "kata satu", 0.9),
        (box(10, 120), "baris dua", 0.9),
    ]

    ordered = sort_reading_order(detections)

    assert [text for _, text, _ in ordered] == [
        "kata satu",
        "kata dua",
        "baris dua",
    ]


def test_sort_reading_order_multi_column_no_interleaving():
    # Left column: x in [10, 50], y at 100 and 200
    # Right column: x in [120, 160], y at 105 and 205
    # Gap = 70 > 0.8 * 10 = 8.0 -> separate columns
    detections = [
        (box(120, 105), "kolom kanan atas", 0.9),
        (box(10, 200), "kolom kiri bawah", 0.9),
        (box(10, 100), "kolom kiri atas", 0.9),
        (box(120, 205), "kolom kanan bawah", 0.9),
    ]

    ordered = sort_reading_order(detections)

    assert [text for _, text, _ in ordered] == [
        "kolom kiri atas",
        "kolom kiri bawah",
        "kolom kanan atas",
        "kolom kanan bawah",
    ]


if __name__ == "__main__":
    test_sort_reading_order_single_column()
    test_sort_reading_order_multi_column_no_interleaving()
    print("ok")

