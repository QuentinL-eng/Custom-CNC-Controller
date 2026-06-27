from cnc_controller.gcode import analyze_gcode_lines, parse_words, strip_comments


def test_strip_comments_handles_semicolon_and_parentheses():
    assert strip_comments("G1 X1 (move) Y2 ; done") == "G1 X1  Y2"


def test_parse_words_extracts_numeric_words():
    assert parse_words("G1 X-1.25 Y.5 F300") == {"G": 1.0, "X": -1.25, "Y": 0.5, "F": 300.0}


def test_analyze_gcode_tracks_bounds_feed_and_power():
    analysis = analyze_gcode_lines(["G21", "G90", "G1 X0 Y0 F400 S250", "G1 X10 Y5", "G91", "G1 X-2 Y3 F600"])
    assert analysis.motion_line_count == 3
    assert analysis.bounds_mm == (0.0, 0.0, 10.0, 8.0)
    assert analysis.max_feed_mm_min == 600
    assert analysis.max_power_s == 250
