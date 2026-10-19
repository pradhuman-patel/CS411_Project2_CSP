"""
UIC CS 411 Project 2: University Class Scheduling (CSP) - Main Entry Point

Instructions for Students:
1. You have complete flexibility in how you design your project folder structure, classes, and helper modules.
2. Implement your scheduling logic inside or called from `studentscheduler()`.
3. Your scheduler should read data dynamically from `data_dir` (default: 'data').
   - If we change or replace the datasets in `data/`, your solution should still work dynamically.
4. Your scheduler must generate the final timetable and save it as `<studentid>_timetable.csv` inside `output_dir` (default: 'data').
5. The function `studentscheduler()` must return the path to the created CSV file.
6. In your report and video presentation, explain how your project directory and architecture are built.
"""

import os
import re
import csv
import sys

# modules are in the same folder as app.py
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from data_loader import load_data
from backtracking_solver import BacktrackingSolver
from local_search import min_conflicts, min_conflicts_soft
from constraints_check import hard_violations, soft_penalty


def get_student_id():
    # get uid from report.md if it is available
    report_path = os.path.join(HERE, "report.md")

    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                content = f.read()

            match = re.search(
                r'-\s*\*\*UID \(netID\):\*\*\s*(.*)',
                content,
                re.IGNORECASE
            )

            if not match:
                match = re.search(
                    r'-\s*\*\*UIN:\*\*\s*(.*)',
                    content,
                    re.IGNORECASE
                )

            if match:
                student_id = match.group(1).strip()

                if student_id and not (
                    student_id.startswith("[") and
                    student_id.endswith("]")
                ):
                    return re.sub(r"[^a-zA-Z0-9_-]", "_", student_id)

        except Exception:
            pass

    return "student"


def find_folder(path):
    # check the current folder first, then the folder containing app.py
    if os.path.isabs(path) or os.path.isdir(path):
        return path

    app_folder = os.path.join(HERE, path)
    if os.path.isdir(app_folder):
        return app_folder

    return path


def write_timetable(path, assignment, data):
    rows = []

    for course_id, (room_id, slot_id) in assignment.items():
        course = data.courses[course_id]
        slot = data.slots[slot_id]

        row = {
            "course_id": course_id,
            "room_id": room_id,
            "slot_id": slot_id,
            "instructor_id": ";".join(course.instructor_ids),
            "cohort_id": ";".join(course.cohorts),
            "day": slot.day,
            "start_time": slot.start_text,
            "end_time": slot.end_text,
            "sort_key": (slot.day_index, slot.start, course_id)
        }

        rows.append(row)

    rows.sort(key=lambda r: r["sort_key"])

    columns = [
        "course_id", "room_id", "slot_id", "instructor_id",
        "cohort_id", "day", "start_time", "end_time"
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)

        for row in rows:
            writer.writerow([row[col] for col in columns])


def studentscheduler(data_dir="data", output_dir="data", student_id=None):
    # set the student id and output folder
    if student_id is None:
        student_id = get_student_id()

    data_dir = find_folder(data_dir)
    output_dir = find_folder(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    output_filename = f"{student_id}_timetable.csv"
    output_path = os.path.join(output_dir, output_filename)

    # load the course, room and time slot data
    data = load_data(data_dir)

    # first try to find a solution using backtracking
    solver = BacktrackingSolver(data)
    assignment = solver.solve()

    # use min conflicts if backtracking can't find a schedule
    no_clashes = True

    if assignment is None:
        print("Backtracking failed, trying min-conflicts")
        assignment, no_clashes = min_conflicts(data)

    # try to improve the soft constraints if the schedule is valid
    if no_clashes:
        assignment, _ = min_conflicts_soft(data, assignment)

    total_penalty, _ = soft_penalty(assignment, data)
    problems = hard_violations(assignment, data)

    print("Scheduled courses:", len(assignment), "/", len(data.courses))
    print("Nodes expanded:", solver.nodes_expanded,
          "Backtracks:", solver.backtracks)
    print("Hard constraint violations:", len(problems))

    for problem in problems[:10]:
        print(" -", problem)

    print("Soft penalty:", total_penalty)

    # save the final schedule
    write_timetable(output_path, assignment, data)

    return output_path


if __name__ == "__main__":
    output_file = studentscheduler()
    print("Timetable generation completed. Output file:", output_file)
