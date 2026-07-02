from __future__ import annotations
from pathlib import Path

from blur import VIDEO_SUFFIXES, _expand_and_clamp, _target_class_ids

COCO_SAMPLE = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
    5: "bus", 6: "train", 7: "truck", 9: "traffic light",
}

def test_target_class_ids_filters_to_people_and_vehicles():
    assert _target_class_ids(
        COCO_SAMPLE, ("person", "car", "truck", "bus", "motorcycle", "bicycle")
    ) == {0, 1, 2, 3, 5, 7}

def test_target_class_ids_person_only():
    assert _target_class_ids(COCO_SAMPLE, ("person",)) == {0}

def test_target_class_ids_empty_when_no_match():
    assert _target_class_ids({0: "cat", 1: "dog"}, ("person",)) == set()

def test_expand_and_clamp_grows_interior_box():
    assert _expand_and_clamp((100, 100, 200, 200), 1000, 1000, margin=0.1) == (90, 90, 210, 210)

def test_expand_and_clamp_clamps_to_frame_bounds():
    assert _expand_and_clamp((5, 5, 50, 50), 100, 100, margin=0.5) == (0, 0, 72, 72)
    assert _expand_and_clamp((960, 960, 1000, 1000), 1000, 1000, margin=0.5) == (940, 940, 1000, 1000)

def test_video_suffix_filter_is_case_insensitive():
    assert Path("flight.MP4").suffix.lower() in VIDEO_SUFFIXES
    assert Path("clip.mov").suffix.lower() in VIDEO_SUFFIXES
    assert Path("notes.txt").suffix.lower() not in VIDEO_SUFFIXES
    assert Path("flight.SRT").suffix.lower() not in VIDEO_SUFFIXES
