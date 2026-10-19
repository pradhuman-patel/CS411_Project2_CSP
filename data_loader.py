
import csv
import json
import os
import re

# default penalty weights, can be changed in sample_constraints.json
DEFAULT_WEIGHTS = {
    "instructor_preference": 10,
    "seat_fit": 5,
    "student_gap": 8,
    "fatigue": 12,
    "transit": 6,
    "room_request": 10,
    "historical_room": 2
}

DEFAULT_ENROLLMENT = 30


def read_csv(path):
    rows = []

    if not os.path.exists(path):
        print("Warning: file not found:", path)
        return rows

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            clean_row = {}

            for column, value in row.items():
                if column is not None:
                    clean_row[column.strip()] = (value or "").strip()

            rows.append(clean_row)

    return rows


def split_list(text):
    if not text:
        return []

    return [item.strip() for item in text.split(";") if item.strip()]


def to_int(value, default=0):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def to_minutes(time_text):
    hours, minutes = time_text.strip().split(":")
    return int(hours) * 60 + int(minutes)


def expand_rooms(text):
    # example: "TECH 201/202/203" becomes separate room ids
    room_list = []

    for part in split_list(text):
        if "/" not in part:
            room_list.append(part)
            continue

        pieces = part.split("/")
        first_room = pieces[0].strip()

        if " " in first_room:
            prefix = first_room.rsplit(" ", 1)[0] + " "
        else:
            prefix = ""

        room_list.append(first_room)

        for number in pieces[1:]:
            if number.strip():
                room_list.append(prefix + number.strip())

    return room_list


class Room:
    def __init__(self, row):
        self.id = row.get("room_id", "")
        self.building = row.get("building", "") or self.id.split(" ")[0]
        self.type = row.get("room_type", "")
        self.features = row.get("features_or_constraints", "")

        physical_capacity = to_int(row.get("physical_capacity"), 0)
        scheduling_capacity = row.get("scheduling_capacity", "")

        if scheduling_capacity == "":
            self.capacity = physical_capacity
        else:
            self.capacity = to_int(scheduling_capacity, 0)

            if 0 < physical_capacity < self.capacity:
                self.capacity = physical_capacity

        availability = row.get("available_for_regular_classes", "Yes").lower()
        self.available = availability in ("yes", "y", "true", "1")
        self.usable = True  # updated after checking room restrictions

    def is_computer_room(self):
        description = (self.type + " " + self.features).lower()
        return "computer" in description or "workstation" in description


class TimeSlot:
    def __init__(self, row, day_index):
        self.id = row.get("slot_id", "")
        self.day = row.get("day", "")
        self.start_text = row.get("start_time", "")
        self.end_text = row.get("end_time", "")
        self.start = to_minutes(self.start_text)
        self.end = to_minutes(self.end_text)
        self.day_index = day_index

    def overlaps(self, other_slot):
        return (
            self.day == other_slot.day
            and self.start < other_slot.end
            and other_slot.start < self.end
        )


class Course:
    def __init__(self, row):
        self.id = row.get("course_id", "")
        self.instructor_names = split_list(row.get("instructors", ""))
        self.instructor_ids = []
        self.historical_rooms = expand_rooms(row.get("rooms_mentioned", ""))
        self.scheduling_context = row.get("scheduling_context", "").lower()
        self.cohorts = []
        self.preferred_rooms = []
        self.needs_computer_room = False
        self.enrollment = 0

        # enrollment may be included in a different version of the csv
        self.given_enrollment = to_int(
            row.get("enrollment") or row.get("expected_enrollment"), 0
        )


class SchedulingData:
    def __init__(self):
        self.courses = {}
        self.rooms = {}
        self.slots = {}
        self.cohorts = {}
        self.cohort_size = {}
        self.instructor_name_to_id = {}
        self.instructor_preferred_slots = {}
        self.instructor_unavailable_slots = {}
        self.banned_rooms = set()
        self.weights = dict(DEFAULT_WEIGHTS)

        self.course_ids = []
        self.domains = {}
        self.overlapping_slots = {}
        self.linked_courses = {}


def load_data(data_dir):
    data = SchedulingData()

    # load the rooms
    for row in read_csv(os.path.join(data_dir, "rooms.csv")):
        if row.get("room_id"):
            room = Room(row)
            data.rooms[room.id] = room

    # load available time slots and keep the day order from the file
    day_order = {}

    for row in read_csv(os.path.join(data_dir, "time_slots.csv")):
        if not row.get("slot_id"):
            continue

        day = row.get("day", "")
        if day not in day_order:
            day_order[day] = len(day_order)

        try:
            slot = TimeSlot(row, day_order[day])
        except ValueError:
            print("Warning: invalid time for slot", row.get("slot_id"))
            continue

        data.slots[slot.id] = slot

    # load courses
    for row in read_csv(os.path.join(data_dir, "courses.csv")):
        if row.get("course_id"):
            course = Course(row)
            data.courses[course.id] = course

    data.course_ids = list(data.courses.keys())

    # read instructor details and preferences
    for row in read_csv(os.path.join(data_dir, "instructors.csv")):
        instructor_id = row.get("instructor_id", "")
        instructor_name = row.get("instructor_name", "")

        if not instructor_id:
            continue

        if instructor_name:
            data.instructor_name_to_id[instructor_name] = instructor_id

        if row.get("preferred_slots"):
            data.instructor_preferred_slots[instructor_id] = set(
                split_list(row["preferred_slots"])
            )

        if row.get("unavailable_slots"):
            data.instructor_unavailable_slots[instructor_id] = set(
                split_list(row["unavailable_slots"])
            )

        # also get courses listed under each instructor
        for course_id in split_list(row.get("courses", "")):
            if course_id in data.courses and instructor_name:
                names = data.courses[course_id].instructor_names

                if instructor_name not in names:
                    names.append(instructor_name)

    # connect instructor names with their ids
    for course in data.courses.values():
        for name in course.instructor_names:
            instructor_id = data.instructor_name_to_id.get(name, name)

            if instructor_id not in course.instructor_ids:
                course.instructor_ids.append(instructor_id)

    # load student cohorts and their required courses
    for row in read_csv(os.path.join(data_dir, "student_cohorts.csv")):
        cohort_id = row.get("cohort_id", "")

        if not cohort_id:
            continue

        data.cohort_size[cohort_id] = to_int(row.get("size"), 0)
        data.cohorts[cohort_id] = []

        for course_id in split_list(row.get("mandatory_courses", "")):
            if course_id in data.courses:
                data.cohorts[cohort_id].append(course_id)
                data.courses[course_id].cohorts.append(cohort_id)

    # read room restrictions and preferred room requests
    for row in read_csv(os.path.join(data_dir, "constraints.csv")):
        rule = row.get("rule", "")
        constraint_type = row.get("constraint_type", "").lower()

        banned_match = re.search(r"room_id\s*!=\s*'([^']+)'", rule)
        if banned_match and constraint_type == "hard":
            data.banned_rooms.add(banned_match.group(1))

        preferred_match = re.search(r"preferred_room\s*=\s*'([^']+)'", rule)
        if preferred_match:
            room_id = preferred_match.group(1)

            for course_id in split_list(row.get("applies_to", "")):
                if course_id in data.courses:
                    data.courses[course_id].preferred_rooms.append(room_id)

    # use custom penalty weights if the json file exists
    json_path = os.path.join(data_dir, "sample_constraints.json")

    if os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8-sig") as f:
                json_data = json.load(f)

            for constraint in json_data.get("soft_constraints", []):
                name = constraint.get("id", "").upper()
                weight = constraint.get("penalty_weight")

                if weight is None:
                    continue
                elif "INSTRUCTOR" in name:
                    data.weights["instructor_preference"] = weight
                elif "SEAT" in name or "UTILIZATION" in name:
                    data.weights["seat_fit"] = weight
                elif "GAP" in name:
                    data.weights["student_gap"] = weight
                elif "FATIGUE" in name or "CONSECUTIVE" in name:
                    data.weights["fatigue"] = weight
                elif "TRANSIT" in name or "BUILDING" in name:
                    data.weights["transit"] = weight

        except (ValueError, OSError):
            print("Warning: unable to read sample_constraints.json, using default weights")

    # mark which rooms can actually be used
    for room in data.rooms.values():
        room.usable = (
            room.available
            and room.capacity > 0
            and room.id not in data.banned_rooms
        )

    work_out_enrollment(data)
    build_domains(data)
    build_overlaps_and_links(data)

    return data


def work_out_enrollment(data):
    # estimate enrollment using the information available for each course
    for course in data.courses.values():
        if course.given_enrollment > 0:
            course.enrollment = course.given_enrollment
            continue

        cohort_sizes = [
            data.cohort_size.get(cohort_id, 0)
            for cohort_id in course.cohorts
        ]

        if cohort_sizes and max(cohort_sizes) > 0:
            course.enrollment = max(cohort_sizes)
            continue

        capacities = []

        for room_id in course.historical_rooms:
            if room_id in data.rooms and data.rooms[room_id].usable:
                capacities.append(data.rooms[room_id].capacity)

        if capacities:
            course.enrollment = min(capacities)
        else:
            course.enrollment = DEFAULT_ENROLLMENT

    # decide whether a course needs a computer room
    for course in data.courses.values():
        parts = [
            part.strip()
            for part in course.scheduling_context.split(";")
        ]

        wants_lab = any(
            part == "computer lab" or part.startswith("lab")
            for part in parts
        )

        if wants_lab:
            for room in data.rooms.values():
                if (
                    room.usable
                    and room.is_computer_room()
                    and room.capacity >= course.enrollment
                ):
                    course.needs_computer_room = True
                    break


def build_domains(data):
    usable_rooms = [
        room for room in data.rooms.values() if room.usable
    ]

    for course_id, course in data.courses.items():
        possible_rooms = [
            room for room in usable_rooms
            if room.capacity >= course.enrollment
        ]

        if course.needs_computer_room:
            # lab courses should use computer rooms
            possible_rooms = [
                room for room in possible_rooms
                if room.is_computer_room()
            ]

        if not possible_rooms and usable_rooms:
            # use the largest rooms if no room has enough capacity
            largest = max(room.capacity for room in usable_rooms)
            possible_rooms = [
                room for room in usable_rooms
                if room.capacity == largest
            ]

            print(
                "Warning:", course_id, "has", course.enrollment,
                "students but the biggest room is", largest
            )

        blocked_slots = set()

        for instructor_id in course.instructor_ids:
            blocked_slots |= data.instructor_unavailable_slots.get(
                instructor_id, set()
            )

        domain = []

        for room in possible_rooms:
            for slot_id in data.slots:
                if slot_id not in blocked_slots:
                    domain.append((room.id, slot_id))

        data.domains[course_id] = domain


def build_overlaps_and_links(data):
    # find which time slots overlap
    for first_slot in data.slots.values():
        data.overlapping_slots[first_slot.id] = set()

        for second_slot in data.slots.values():
            if first_slot.overlaps(second_slot):
                data.overlapping_slots[first_slot.id].add(second_slot.id)

    # link courses that share an instructor or a student cohort
    for course_id in data.course_ids:
        data.linked_courses[course_id] = set()

    for index, first_id in enumerate(data.course_ids):
        first_course = data.courses[first_id]

        for second_id in data.course_ids[index + 1:]:
            second_course = data.courses[second_id]

            same_instructor = (
                set(first_course.instructor_ids)
                & set(second_course.instructor_ids)
            )
            same_cohort = (
                set(first_course.cohorts)
                & set(second_course.cohorts)
            )

            if same_instructor or same_cohort:
                data.linked_courses[first_id].add(second_id)
                data.linked_courses[second_id].add(first_id)
