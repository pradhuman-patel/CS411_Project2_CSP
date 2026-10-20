# Project 2 Report: University Class Scheduling & Timetable Optimization

> [!IMPORTANT]
> **AUTOGRADER COMPLIANCE INSTRUCTIONS:**
> This report is parsed automatically by the autograder. To ensure you receive full credit for your work:
>
> 1. **Do not modify** the section headers (`## ...`) or bold field keys (e.g., `**Name:**`, `**Total Courses Configured:**`, `**Video Presentation Link:**`, etc.).
> 2. **Write your answers directly after** the colon `:` of each field, replacing the placeholder text completely (including the outer brackets `[` and `]`).
> 3. **Maintain the file structure**. Changing headers, bold titles, or deleting lines can cause the autograder to miss your responses and award 0 marks.

---

## Student Information

- **Name:** Pradhuman Patel
- **UID (netID):** ppate575
- **UIN:** 660584048

---

## Section 1: Dataset & University Configuration

- **Total Courses Configured:** 65
- **Total Rooms Configured:** 20
- **Total Time Slots Configured:** 50

---

## Section 2: Local Verification & Implemented Solvers

_Check the algorithms and features you successfully ran and verified by placing an `x` in the brackets (e.g., `[x]`):_

- [x] DataLoader & CSV Parsing
- [x] Hard Constraint Validation Engine
- [x] Soft Penalty & Quality Evaluation Engine
- [x] CSP Backtracking with MRV + LCV + Forward Checking
- [x] Min-Conflicts CSP Local Search
- [x] Timetable CSV Export (<studentid>\_timetable.csv)

---

## Section 3: Video Presentation & Project Structure

- **Video Presentation Link:** https://drive.google.com/file/d/11lcJlvl-6joS_k4yi5qxCTwXUAbYRTe5/view?usp=sharing
- **Project Directory Structure:** Plain Python modules in the project root with app.py as the entry point and data/ for the inputs and output:

```
    Project02_CSP/
    ├── app.py                  # studentscheduler(): runs the pipeline, writes <netID>_timetable.csv
    ├── data_loader.py          # reads the CSVs + json, builds variables, domains, overlaps, linked courses
    ├── constraints_check.py    # hard constraint checks, final verification, soft penalty (S1-S5)
    ├── backtracking_solver.py  # BacktrackingSolver: MRV + degree, LCV, forward checking
    ├── local_search.py         # min_conflicts_soft (soft penalty) + min_conflicts (hard backup)
    ├── report.md
    └── data/
        ├── courses.csv, instructors.csv, rooms.csv, time_slots.csv
        ├── student_cohorts.csv, constraints.csv, sample_constraints.json
        └── ppate575_timetable.csv   # output
```

---

## Section 4: Discussion & Problem Formulation

_Provide your written analysis for each point by replacing the bracket placeholders below:_

- **How did you formulate the variables, domains, and constraints for this scheduling problem?**
  Each course is a variable (65 in total). The domain of a course is every (room, time slot) pair that is allowed for it: the room must be available, big enough for the class, and a computer room if it is a lab course. LAB 254 is excluded because it is the testing center. Since courses.csv has no enrollment, I estimated it from the cohort size or the historical room size. The hard constraints are: no room used twice at the same time, no instructor teaching two classes at once, and no cohort with two mandatory classes at the same time. I check these with real start and end times because some slots overlap. The soft constraints (S1-S5, room requests and historical rooms) add a weighted penalty, using the weights from sample_constraints.json.
- **Compare CSP Backtracking (with heuristics) vs Local Search (Min-Conflicts) in terms of scalability, completeness, and solution quality.**
  Backtracking is complete: it always finds a solution if one exists. But it can be very slow on big or tight problems. MRV, the degree heuristic, LCV and forward checking make it much faster; here it needed only 65 nodes and 0 backtracks. However, it only cares about hard constraints, so its timetable had a soft penalty of 180. Min-Conflicts is not complete and can get stuck, but it scales better because it only changes one course at a time. It improved the penalty from 180 to 32, which is the best possible for this data. Using both together works best: backtracking gives a valid timetable, and Min-Conflicts makes it better.
- **How can modern AI / LLM techniques be combined with CSP solvers for real-world automated university scheduling?**
  An LLM can read messy input, like instructor emails or notes such as "prefers mornings", and turn it into constraints for the solver. The CSP solver then makes sure the final timetable has no clashes, so mistakes from the LLM can't break the schedule. The LLM can also explain the result in simple words, for example why a course didn't get its requested room, and turn change requests into new constraints. Machine learning can also help by predicting enrollment from past terms. Basically, the LLM suggests and the CSP solver checks.
