import pytest
from vitals import _sparkline, GREEN, RED, BLUE, CYAN, RESET

def test_sparkline_empty():
    assert _sparkline(0, 0, 0, width=10) == f"{CYAN}[----------]{RESET}"

def test_sparkline_proportions():
    # 30 blocks total
    # 10s working (1/3), 10s hanging (1/3), 10s waiting (1/3) -> 10, 10, 10 blocks
    bar = _sparkline(10, 10, 10, width=30)
    assert bar.count("■") == 30
    assert f"{GREEN}{'■' * 10}" in bar
    assert f"{RED}{'■' * 10}" in bar
    assert f"{BLUE}{'■' * 10}" in bar

def test_sparkline_rounding_small_values():
    # Total 100s. 95s working (28.5 -> 29), 4s hanging (1.2 -> 1), 1s waiting (0.3 -> 0)
    # The logic ensures at least 1 block if duration > 0
    bar = _sparkline(95, 4, 1, width=30)
    assert bar.count("■") == 30
    # Waiting (1s) should get 1 block because of the safety check
    assert f"{BLUE}■" in bar

def test_sparkline_ordering():
    # Working 10, Hanging 20, Waiting 5 -> Order should be Hanging, Working, Waiting
    bar = _sparkline(10, 20, 5, width=30)
    # RED (Hanging) is 20/35 * 30 = 17.1 -> 17 blocks
    # GREEN (Working) is 10/35 * 30 = 8.5 -> 9 blocks
    # BLUE (Waiting) is 5/35 * 30 = 4.2 -> 4 blocks
    # 17 + 9 + 4 = 30.
    red_pos = bar.find(RED)
    green_pos = bar.find(GREEN)
    blue_pos = bar.find(BLUE)
    assert red_pos < green_pos < blue_pos

def test_sparkline_adjustment_on_largest():
    # 33.3, 33.3, 33.3 -> 10, 10, 10. Sum 30.
    # What if 33.4, 33.3, 33.3?
    # int(round(30 * 0.334)) = 10
    # int(round(30 * 0.333)) = 10
    # Difference = 0.
    
    # 51% (15.3->15), 49% (14.7->15). Sum 30.
    bar = _sparkline(51, 49, 0, width=30)
    assert bar.count("■") == 30
