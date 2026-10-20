
import csv
import json
import os
import re


# default penalty weights; the json file can override some of these
DEFAULT_WEIGHTS = {
    "instructor_preference": 10,
    "seat_fit": 5,
    "student_gap": 8,
    "fatigue": 12,
    "transit": 6,
    "room_request": 10,
    "historical_room": 2,
}

DEFAULT_ENROLLMENT = 30


def read_csv(path):
    rows = []

    if not os.path.exists(path):
        print("Warning: could not find", path)
        return rows

    with open(path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            cleaned = {}

            for column, value in row.items():
                if column is None:
                    continue

                name = column.strip().lower().replace(" ", "_")
                cleaned[name] = (value or "").strip()

            rows.append(cleaned)

    return rows


def get_value(row, *possible_names):
    # column names can differ between datasets
    for name in possible_names:
        value = row.get(name, "")
        if value != "":
            return value

    return ""


def split_list(text):
    if not text:
        return []

    return [
        item.strip()
        for item in re.split(r"[;,|]", text)
        if item.strip()
    ]


def to_int(value, default=0):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def to_minutes(time_text):
    # convert times like 08:00, 8:00 AM, 2:15pm, or 0800 to minutes
    text = time_text.strip().lower().replace(".", "")
    is_pm = text.endswith("pm")
    is_am = text.endswith("am")
    text = text.replace("am", "").replace("pm", "").strip()

    if ":" in text:
        parts = text.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
    elif len(text) >= 3:
        hours = int(text[:-2])
        minutes = int(text[-2:])
    else:
        hours = int(text)
        minutes = 0

    if is_pm and hours < 12:
        hours += 12
    if is_am and hours == 12:
        hours = 0

    return hours * 60 + minutes


def expand_rooms(text):
    # expand room lists like "TECH 201/202/203" into full room names
    rooms = []

    for part in split_list(text):
        if "/" not in part:
            rooms.append(part)
            continue

        pieces = part.split("/")
        first_room = pieces[0].strip()

        if " " in first_room:
            prefix = first_room.rsplit(" ", 1)[0] + " "
        else:
            prefix = ""

        rooms.append(first_room)

        for room_number in pieces[1:]:
            room_number = room_number.strip()
            if room_number:
                rooms.append(prefix + room_number)

    return rooms


class Room:
    def __init__(self, row):
        self.id = get_value(
            row, "room_id", "id", "room", "room_name", "name"
        )
        self.building = (
            get_value(row, "building", "building_name")
            or self.id.split(" ")[0]
        )
        self.type = get_value(row, "room_type", "type")
        self.features = get_value(
            row, "features_or_constraints", "features"
        )

        physical_capacity = to_int(
            get_value(row, "physical_capacity", "capacity", "seats", "size"),
            0,
        )
        scheduling_capacity = get_value(row, "scheduling_capacity")

        if scheduling_capacity == "":
            self.capacity = physical_capacity
        else:
            self.capacity = to_int(scheduling_capacity, 0)

            if 0 < physical_capacity < self.capacity:
                self.capacity = physical_capacity

        availability = (
            get_value(
                row,
                "available_for_regular_classes",
                "available",
                "availability",
            )
            or "Yes"
        )
        self.available = availability.lower() in (
            "yes", "y", "true", "1"
        )

        # updated later after banned rooms are loaded
        self.usable = True

    def is_computer_room(self):
        description = (self.type + " " + self.features).lower()
        return "computer" in description or "workstation" in description


class TimeSlot:
    def __init__(self, row, day_index):
        self.id = get_value(
            row, "slot_id", "id", "time_slot_id", "timeslot_id", "slot"
        )
        self.day = get_value(row, "day", "weekday", "day_of_week")
        self.start_text = get_value(row, "start_time", "start", "begin")
        self.end_text = get_value(row, "end_time", "end", "finish")

        self.start = to_minutes(self.start_text)

        if self.end_text:
            self.end = to_minutes(self.end_text)
        else:
            self.end = self.start + 50

        self.day_index = day_index

    def overlaps(self, other_slot):
        return (
            self.day == other_slot.day
            and self.start < other_slot.end
            and other_slot.start < self.end
        )


class Course:
    def __init__(self, row):
        self.id = get_value(
            row, "course_id", "id", "course", "course_code", "code"
        )
        self.instructor_names = split_list(
            get_value(
                row,
                "instructors",
                "instructor",
                "instructor_id",
                "instructor_ids",
                "instructor_name",
            )
        )
        self.instructor_ids = []

        self.historical_rooms = expand_rooms(
            get_value(
                row,
                "rooms_mentioned",
                "preferred_rooms",
                "preferred_room",
                "room",
            )
        )
        self.scheduling_context = get_value(
            row,
            "scheduling_context",
            "course_type",
            "type",
            "activity_type",
            "required_room_type",
        ).lower()

        self.cohorts = []
        self.preferred_rooms = []
        self.needs_computer_room = False
        self.enrollment = 0

        # enrollment is optional in the input file
        self.given_enrollment = to_int(
            get_value(
                row,
                "enrollment",
                "expected_enrollment",
                "students",
                "num_students",
                "size",
                "class_size",
            ),
            0,
        )
        self.given_cohorts = split_list(
            get_value(row, "cohort_id", "cohort", "cohorts")
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

    # load rooms
    for row in read_csv(os.path.join(data_dir, "rooms.csv")):
        room = Room(row)
        if room.id:
            data.rooms[room.id] = room

    # keep the day order from the time slot file
    day_order = {}

    for row in read_csv(os.path.join(data_dir, "time_slots.csv")):
        day = get_value(row, "day", "weekday", "day_of_week")

        if day not in day_order:
            day_order[day] = len(day_order)

        try:
            slot = TimeSlot(row, day_order[day])
        except (ValueError, IndexError):
            print("Warning: bad time in slot", row)
            continue

        if slot.id:
            data.slots[slot.id] = slot

    # load courses
    for row in read_csv(os.path.join(data_dir, "courses.csv")):
        course = Course(row)
        if course.id:
            data.courses[course.id] = course

    data.course_ids = list(data.courses.keys())

    # load instructor information
    for row in read_csv(os.path.join(data_dir, "instructors.csv")):
        instructor_id = get_value(row, "instructor_id", "id")
        instructor_name = get_value(row, "instructor_name", "name")

        if not instructor_id:
            instructor_id = instructor_name
        if not instructor_id:
            continue

        data.instructor_name_to_id[instructor_id] = instructor_id

        if instructor_name:
            data.instructor_name_to_id[instructor_name] = instructor_id

        preferred = get_value(
            row,
            "preferred_slots",
            "preferred_times",
            "preferences",
            "teaching_preferences",
        )
        if preferred:
            data.instructor_preferred_slots[instructor_id] = set(
                split_list(preferred)
            )

        unavailable = get_value(
            row, "unavailable_slots", "unavailable_times", "unavailable"
        )
        if unavailable:
            data.instructor_unavailable_slots[instructor_id] = set(
                split_list(unavailable)
            )

        # instructor files can also list the courses they teach
        course_list = split_list(
            get_value(row, "courses", "course_ids", "assigned_courses")
        )

        for course_id in course_list:
            if course_id in data.courses and instructor_name:
                names = data.courses[course_id].instructor_names
                if instructor_name not in names:
                    names.append(instructor_name)

    # match instructor names to their IDs
    for course in data.courses.values():
        for name in course.instructor_names:
            instructor_id = data.instructor_name_to_id.get(name, name)

            if instructor_id not in course.instructor_ids:
                course.instructor_ids.append(instructor_id)

    # load student cohorts and their required courses
    for row in read_csv(os.path.join(data_dir, "student_cohorts.csv")):
        cohort_id = get_value(row, "cohort_id", "id", "cohort", "name")

        if not cohort_id:
            continue

        data.cohort_size[cohort_id] = to_int(
            get_value(
                row, "size", "student_count", "students", "num_students"
            ),
            0,
        )
        data.cohorts.setdefault(cohort_id, [])

        required_courses = split_list(
            get_value(
                row,
                "mandatory_courses",
                "courses",
                "required_courses",
            )
        )

        for course_id in required_courses:
            if (
                course_id in data.courses
                and course_id not in data.cohorts[cohort_id]
            ):
                data.cohorts[cohort_id].append(course_id)
                data.courses[course_id].cohorts.append(cohort_id)

    # some files list cohorts directly in courses.csv
    for course_id, course in data.courses.items():
        for cohort_id in course.given_cohorts:
            data.cohorts.setdefault(cohort_id, [])

            if course_id not in data.cohorts[cohort_id]:
                data.cohorts[cohort_id].append(course_id)
                course.cohorts.append(cohort_id)

    # read hard room restrictions and preferred room requests
    for row in read_csv(os.path.join(data_dir, "constraints.csv")):
        rule = get_value(row, "rule")
        constraint_type = get_value(
            row, "constraint_type", "type"
        ).lower()

        banned_match = re.search(r"room_id\s*!=\s*'([^']+)'", rule)

        if banned_match and constraint_type == "hard":
            data.banned_rooms.add(banned_match.group(1))

        preferred_match = re.search(
            r"preferred_room\s*=\s*'([^']+)'", rule
        )

        if preferred_match:
            room_id = preferred_match.group(1)

            for course_id in split_list(get_value(row, "applies_to")):
                if course_id in data.courses:
                    data.courses[course_id].preferred_rooms.append(room_id)

    # update soft constraint weights if the json file exists
    json_path = os.path.join(data_dir, "sample_constraints.json")

    if os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8-sig") as file:
                json_data = json.load(file)

            for constraint in json_data.get("soft_constraints", []):
                name = constraint.get("id", "").upper()
                weight = constraint.get("penalty_weight")

                if weight is None:
                    continue

                if "INSTRUCTOR" in name:
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
            print(
                "Warning: could not read sample_constraints.json, "
                "using default weights"
            )

    # mark rooms that can be used for scheduling
    for room in data.rooms.values():
        room.usable = (
            room.available
            and room.capacity > 0
            and room.id not in data.banned_rooms
        )

    if data.rooms and not any(room.usable for room in data.rooms.values()):
        print("Warning: no usable rooms found, using all rooms")

        for room in data.rooms.values():
            room.usable = room.id not in data.banned_rooms

            if room.capacity <= 0:
                room.capacity = DEFAULT_ENROLLMENT

    print(
        "Loaded",
        len(data.courses),
        "courses,",
        len(data.rooms),
        "rooms,",
        len(data.slots),
        "time slots",
    )

    work_out_enrollment(data)
    build_domains(data)
    build_overlaps_and_links(data)

    return data


def work_out_enrollment(data):
    # estimate enrollment from the available information
    # use: given enrollment, largest cohort, historical room, or default
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

        historical_capacities = []

        for room_id in course.historical_rooms:
            if room_id in data.rooms and data.rooms[room_id].usable:
                historical_capacities.append(
                    data.rooms[room_id].capacity
                )

        if historical_capacities:
            course.enrollment = min(historical_capacities)
        else:
            course.enrollment = DEFAULT_ENROLLMENT

    # check which courses need computer labs
    for course in data.courses.values():
        context_parts = [
            part.strip()
            for part in course.scheduling_context.split(";")
        ]
        wants_lab = any(
            part == "computer lab" or part.startswith("lab")
            for part in context_parts
        )

        if not wants_lab:
            continue

        # only require a computer room if one has enough seats
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
            possible_rooms = [
                room for room in possible_rooms
                if room.is_computer_room()
            ]

        if not possible_rooms and usable_rooms:
            # use the largest rooms if none have enough capacity
            biggest_capacity = max(
                room.capacity for room in usable_rooms
            )
            possible_rooms = [
                room for room in usable_rooms
                if room.capacity == biggest_capacity
            ]

            print(
                "Warning:",
                course_id,
                "has",
                course.enrollment,
                "students but biggest room is",
                biggest_capacity,
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

        if not domain:
            # keep a domain even if all listed slots were blocked
            domain = [
                (room.id, slot_id)
                for room in possible_rooms
                for slot_id in data.slots
            ]

        data.domains[course_id] = domain


def build_overlaps_and_links(data):
    # find which time slots overlap
    for first_slot in data.slots.values():
        data.overlapping_slots[first_slot.id] = set()

        for second_slot in data.slots.values():
            if first_slot.overlaps(second_slot):
                data.overlapping_slots[first_slot.id].add(second_slot.id)

    # courses are linked if they share an instructor or student cohort
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
