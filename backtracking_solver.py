
import sys
import time
from collections import defaultdict

from constraints_check import is_consistent, value_cost


class BacktrackingSolver:
    # solve the schedule using backtracking and a few CSP heuristics

    def __init__(self, data, node_limit=200000, time_limit=15):
        self.data = data
        self.node_limit = node_limit
        self.time_limit = time_limit
        self.nodes_expanded = 0
        self.backtracks = 0
        self.gave_up = False
        self.start_time = 0

        # calculate the cost for each possible course assignment
        self.cost = {}
        for course_id in data.course_ids:
            for value in data.domains[course_id]:
                self.cost[(course_id, value)] = value_cost(
                    course_id, value, data
                )

    def solve(self):
        self.start_time = time.time()

        # allow enough recursion for larger schedules
        needed_limit = len(self.data.course_ids) + 500
        if sys.getrecursionlimit() < needed_limit:
            sys.setrecursionlimit(needed_limit)

        domains = {
            course_id: list(self.data.domains[course_id])
            for course_id in self.data.course_ids
        }

        for course_id, domain in domains.items():
            if not domain:
                print("Course", course_id, "does not have any available options")
                return None

        assignment = {}
        unassigned = set(self.data.course_ids)

        if self.backtrack(assignment, domains, unassigned):
            return assignment

        return None

    def select_variable(self, unassigned, domains):
        # choose the course with the fewest options first (MRV)
        # if tied, choose the course connected to more other courses
        return min(
            unassigned,
            key=lambda course_id: (
                len(domains[course_id]),
                -len(self.data.linked_courses[course_id]),
                course_id
            )
        )

    def order_values(self, course_id, domain, domains, unassigned):
        # try assignments that rule out fewer choices for other courses
        data = self.data
        linked = data.linked_courses[course_id]

        # count possible values to make checking each option faster
        room_slot_count = defaultdict(int)
        slot_count = defaultdict(int)

        for other_id in unassigned:
            if other_id in linked:
                for other_value in domains[other_id]:
                    slot_count[other_value[1]] += 1
            else:
                for other_value in domains[other_id]:
                    room_slot_count[other_value] += 1

        def values_removed(value):
            room_id, slot_id = value
            count = 0

            for other_slot in data.overlapping_slots[slot_id]:
                count += room_slot_count[(room_id, other_slot)]
                count += slot_count[other_slot]

            return count

        enrollment = data.courses[course_id].enrollment

        return sorted(
            domain,
            key=lambda value: (
                values_removed(value),
                self.cost[(course_id, value)],
                data.rooms[value[0]].capacity - enrollment,
                data.slots[value[1]].day_index,
                data.slots[value[1]].start
            )
        )

    def forward_check(self, course_id, value, domains, unassigned):
        room_id, slot_id = value
        overlapping = self.data.overlapping_slots[slot_id]
        linked = self.data.linked_courses[course_id]

        removed = []

        for other_id in unassigned:
            is_linked = other_id in linked
            keep = []
            dropped = []

            for other_value in domains[other_id]:
                same_time = other_value[1] in overlapping
                same_room = other_value[0] == room_id

                if same_time and (is_linked or same_room):
                    dropped.append(other_value)
                else:
                    keep.append(other_value)

            if dropped:
                domains[other_id] = keep
                removed.append((other_id, dropped))

                # no options left means this choice cannot work
                if not keep:
                    return removed, False

        return removed, True

    def backtrack(self, assignment, domains, unassigned):
        if not unassigned:
            return True

        elapsed = time.time() - self.start_time
        if self.nodes_expanded >= self.node_limit or elapsed > self.time_limit:
            self.gave_up = True
            return False

        self.nodes_expanded += 1

        course_id = self.select_variable(unassigned, domains)
        unassigned.remove(course_id)

        options = self.order_values(
            course_id, domains[course_id], domains, unassigned
        )

        for value in options:
            if not is_consistent(course_id, value, assignment, self.data):
                continue

            assignment[course_id] = value

            removed, valid = self.forward_check(
                course_id, value, domains, unassigned
            )

            if valid and self.backtrack(assignment, domains, unassigned):
                return True

            # restore the choices removed by forward checking
            for other_id, dropped in removed:
                domains[other_id].extend(dropped)

            del assignment[course_id]

            if self.gave_up:
                break

            self.backtracks += 1

        unassigned.add(course_id)
        return False
