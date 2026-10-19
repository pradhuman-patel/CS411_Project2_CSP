
from collections import defaultdict


def is_consistent(course_id, value, assignment, data):
    # check if this course conflicts with anything already scheduled
    room_id, slot_id = value
    overlapping = data.overlapping_slots[slot_id]

    for other_id, (other_room, other_slot) in assignment.items():
        if other_id == course_id or other_slot not in overlapping:
            continue

        if room_id == other_room:
            return False

        if other_id in data.linked_courses[course_id]:
            return False

    return True


def count_conflicts(course_id, value, assignment, data):
    room_id, slot_id = value
    overlapping = data.overlapping_slots[slot_id]
    conflicts = 0

    for other_id, (other_room, other_slot) in assignment.items():
        if other_id == course_id or other_slot not in overlapping:
            continue

        if room_id == other_room or other_id in data.linked_courses[course_id]:
            conflicts += 1

    return conflicts


def hard_violations(assignment, data):
    problems = []

    # check if every course has a valid room and time
    for course_id in data.course_ids:
        if course_id not in assignment:
            problems.append(course_id + " is not scheduled")
            continue

        room_id, slot_id = assignment[course_id]
        course = data.courses[course_id]
        room = data.rooms.get(room_id)

        if room is None or not room.usable:
            problems.append(
                course_id + " is in a room that can't be used: " + room_id
            )
        elif course.enrollment > room.capacity:
            problems.append(
                course_id + " has too many students for " + room_id
            )
        elif course.needs_computer_room and not room.is_computer_room():
            problems.append(
                course_id + " is a lab course but " + room_id +
                " is not a computer room"
            )

        for instructor_id in course.instructor_ids:
            unavailable = data.instructor_unavailable_slots.get(
                instructor_id, set()
            )
            if slot_id in unavailable:
                problems.append(
                    course_id + " instructor " + instructor_id +
                    " is unavailable at " + slot_id
                )

    # check for room and instructor/cohort clashes
    scheduled = [
        course_id for course_id in data.course_ids
        if course_id in assignment
    ]

    for index, first_id in enumerate(scheduled):
        first_room, first_slot = assignment[first_id]

        for second_id in scheduled[index + 1:]:
            second_room, second_slot = assignment[second_id]

            if second_slot not in data.overlapping_slots[first_slot]:
                continue

            if first_room == second_room:
                problems.append(
                    first_id + " and " + second_id +
                    " clash in room " + first_room
                )
            elif second_id in data.linked_courses[first_id]:
                problems.append(
                    first_id + " and " + second_id +
                    " share instructor/cohort at same time"
                )

    return problems


def value_cost(course_id, value, data):
    # give each option a cost based on the course preferences
    room_id, slot_id = value
    course = data.courses[course_id]
    room = data.rooms[room_id]
    weights = data.weights

    cost = 0

    for instructor_id in course.instructor_ids:
        preferred = data.instructor_preferred_slots.get(instructor_id)
        if preferred and slot_id not in preferred:
            cost += weights["instructor_preference"]

    if room.capacity - course.enrollment > 30:
        cost += weights["seat_fit"]

    if course.preferred_rooms and room_id not in course.preferred_rooms:
        cost += weights["room_request"]

    if course.historical_rooms and room_id not in course.historical_rooms:
        cost += weights["historical_room"]

    return cost


def sessions_by_day(groups, assignment, data):
    # organize scheduled classes by group and day
    result = {}

    for group_name, course_list in groups.items():
        days = defaultdict(list)

        for course_id in course_list:
            if course_id not in assignment:
                continue

            room_id, slot_id = assignment[course_id]
            slot = data.slots[slot_id]
            building = data.rooms[room_id].building

            days[slot.day].append(
                (slot.start, slot.end, building, course_id)
            )

        for day in days:
            days[day].sort()

        result[group_name] = days

    return result


def score_schedule(assignment, data):
    # calculate the penalties and keep track of the courses involved
    weights = data.weights

    penalties = {
        "S1_instructor_preference": 0,
        "S2_seat_utilization": 0,
        "S3_student_gaps": 0,
        "S4_consecutive_fatigue": 0,
        "S5_building_transit": 0,
        "room_requests": 0,
        "historical_rooms": 0
    }

    blame = defaultdict(int)

    def add_penalty(name, amount, course_list):
        penalties[name] += amount

        for course_id in course_list:
            blame[course_id] += amount

    # check the preferences for each scheduled course
    for course_id, (room_id, slot_id) in assignment.items():
        course = data.courses[course_id]
        room = data.rooms[room_id]

        for instructor_id in course.instructor_ids:
            preferred = data.instructor_preferred_slots.get(instructor_id)

            if preferred and slot_id not in preferred:
                add_penalty(
                    "S1_instructor_preference",
                    weights["instructor_preference"],
                    [course_id]
                )

        if room.capacity - course.enrollment > 30:
            add_penalty(
                "S2_seat_utilization", weights["seat_fit"], [course_id]
            )

        if course.preferred_rooms and room_id not in course.preferred_rooms:
            add_penalty("room_requests", weights["room_request"], [course_id])

        if course.historical_rooms and room_id not in course.historical_rooms:
            add_penalty(
                "historical_rooms", weights["historical_room"], [course_id]
            )

    cohort_days = sessions_by_day(data.cohorts, assignment, data)

    teaching = defaultdict(list)
    for course_id in data.course_ids:
        for instructor_id in data.courses[course_id].instructor_ids:
            teaching[instructor_id].append(course_id)

    instructor_days = sessions_by_day(teaching, assignment, data)

    # classes with 15 minutes or less between them count as back to back
    for days in cohort_days.values():
        for sessions in days.values():
            in_a_row = 1

            for index in range(1, len(sessions)):
                previous = sessions[index - 1]
                current = sessions[index]

                if current[0] - previous[1] <= 15:
                    in_a_row += 1

                    if in_a_row > 2:
                        add_penalty(
                            "S4_consecutive_fatigue",
                            weights["fatigue"],
                            [previous[3], current[3]]
                        )

                    if current[2] != previous[2]:
                        add_penalty(
                            "S5_building_transit",
                            weights["transit"],
                            [previous[3], current[3]]
                        )
                else:
                    in_a_row = 1
                    add_penalty(
                        "S3_student_gaps",
                        weights["student_gap"],
                        [previous[3], current[3]]
                    )

    # also check consecutive classes for instructors
    for days in instructor_days.values():
        for sessions in days.values():
            in_a_row = 1

            for index in range(1, len(sessions)):
                previous = sessions[index - 1]
                current = sessions[index]

                if current[0] - previous[1] <= 15:
                    in_a_row += 1

                    if in_a_row > 2:
                        add_penalty(
                            "S4_consecutive_fatigue",
                            weights["fatigue"],
                            [previous[3], current[3]]
                        )
                else:
                    in_a_row = 1

    return penalties, blame


def soft_penalty(assignment, data):
    penalties, _ = score_schedule(assignment, data)
    total = sum(penalties.values())

    return total, penalties
