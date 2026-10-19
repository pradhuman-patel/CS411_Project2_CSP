# Project 2 Report: University Class Scheduling & Timetable Optimization

> [!IMPORTANT]
> **AUTOGRADER COMPLIANCE INSTRUCTIONS:**
> This report is parsed automatically by the autograder. To ensure you receive full credit for your work:
> 1. **Do not modify** the section headers (`## ...`) or bold field keys (e.g., `**Name:**`, `**Total Courses Configured:**`, `**Video Presentation Link:**`, etc.).
> 2. **Write your answers directly after** the colon `:` of each field, replacing the placeholder text completely (including the outer brackets `[` and `]`).
> 3. **Maintain the file structure**. Changing headers, bold titles, or deleting lines can cause the autograder to miss your responses and award 0 marks.

---

## Student Information 
- **Name:** «YOUR FULL NAME»
- **UID (netID):** ppate575
- **UIN:** «YOUR UIN»

---

## Section 1: Dataset & University Configuration
- **Total Courses Configured:** 65
- **Total Rooms Configured:** 20
- **Total Time Slots Configured:** 50

---

## Section 2: Local Verification & Implemented Solvers
*Check the algorithms and features you successfully ran and verified by placing an `x` in the brackets (e.g., `[x]`):*
- [x] DataLoader & CSV Parsing
- [x] Hard Constraint Validation Engine
- [x] Soft Penalty & Quality Evaluation Engine
- [x] CSP Backtracking with MRV + LCV + Forward Checking
- [x] Min-Conflicts CSP Local Search
- [x] Timetable CSV Export (<studentid>_timetable.csv)

---

## Section 3: Video Presentation & Project Structure
- **Video Presentation Link:** «YOUR VIDEO LINK»
- **Project Directory Structure:** All code is in plain Python modules in the project root (no package), next to the data/ folder. app.py is the entry point: studentscheduler() reads the netID from this report, loads the data, runs the solvers and writes data/<netID>_timetable.csv with the columns course_id, room_id, slot_id, instructor_id, cohort_id, day, start_time, end_time. data_loader.py reads all the CSV files (and sample_constraints.json for the soft weights) by column name into Room, TimeSlot, Course and SchedulingData classes, estimates enrollment, and builds the CSP domains, the overlapping-slot table and the linked-course table. constraints_check.py is the constraint engine: is_consistent() and count_conflicts() for the hard binary constraints, hard_violations() to verify the final timetable, and score_schedule()/soft_penalty() for S1-S5 plus the room preferences from constraints.csv. backtracking_solver.py contains the BacktrackingSolver class (MRV with degree tie-break, LCV and forward checking). local_search.py contains min_conflicts_soft() for soft penalty minimization and min_conflicts() as a backup for hard constraints if backtracking hits its node/time limit. app.py adds its own folder to sys.path so it still works when the grader runs it from a different directory, and since every file is read by column name the scheduler still works when the datasets in data/ are changed.

---

## Section 4: Discussion & Problem Formulation
*Provide your written analysis for each point by replacing the bracket placeholders below:*
- **How did you formulate the variables, domains, and constraints for this scheduling problem?**
    Each of the 65 courses is one variable. The domain of a course is every (room, time slot) pair that already passes the unary hard constraints: the room must be available for regular classes and not banned (LAB 254 is read from the room_id != 'LAB 254' rule in constraints.csv), the room's scheduling capacity must be at least the course enrollment, lab courses can only use computer rooms (LAB 201, TECH 106), and the slot cannot be in an instructor's unavailable slots. courses.csv has no enrollment, so I estimate it from the size of the largest cohort that must take the course (e.g. CS 141 = 150 from CS_Y1), otherwise from the smallest historical room in rooms_mentioned, otherwise 30. The binary hard constraints are: no two courses in the same room at overlapping times (H1), no instructor teaching two overlapping courses (H3), and no cohort with two overlapping mandatory courses (H5). Overlap is checked with real start and end times, because some slots overlap (e.g. MON_S6 13:00-14:15 and MON_S7 14:00-15:15). Two courses are "linked" if they share an instructor or a cohort, and linked courses can never overlap. H6 holds because every course is a variable and must get a value. The soft constraints form a weighted penalty, with weights from sample_constraints.json: S1 instructor preferred slots (10), S2 more than 30 empty seats (5), S3 idle gaps in a cohort's day (8), S4 more than two back-to-back classes (12) and S5 back-to-back classes in different buildings (6). Room requests from constraints.csv (10) and historical rooms (2) are added as extra soft penalties.
- **Compare CSP Backtracking (with heuristics) vs Local Search (Min-Conflicts) in terms of scalability, completeness, and solution quality.**
    Backtracking is complete: if a solution exists it will find it, and if it explores everything it proves there is none. In the worst case its cost is exponential, so it scales badly on tight or very large problems. The heuristics are what make it practical. MRV with the degree tie-break picks the hardest course first, LCV tries the value that removes the fewest options from the other courses, and forward checking finds dead ends early. On this data it found a valid timetable in 65 nodes with 0 backtracks. Backtracking only guarantees feasibility, though, not quality: the first timetable had a soft penalty of 180, because LCV chooses values that keep the search easy rather than ones that lower the penalty. Min-Conflicts is incomplete: it can get stuck in local minima and can never prove a problem has no solution. But each step only looks at one course, so it scales much better and works as an anytime algorithm that keeps the best timetable found so far. Starting from the backtracking solution and only allowing moves that keep every hard constraint, Min-Conflicts lowered the penalty from 180 to 32 in about 430 steps. 32 is optimal here, because adding each course's cheapest possible cost on its own also gives 32. The remaining penalty is unavoidable: CS 107 requests CAMPUS-CTR 137, but as a lab course it must be in a computer room, and several large courses can't fit in their historical rooms. Using both together works best: backtracking for a guaranteed feasible start, and local search to improve quality.
- **How can modern AI / LLM techniques be combined with CSP solvers for real-world automated university scheduling?**
    LLMs are good with language but unreliable at exact constraint reasoning, while CSP solvers are exact but need formal input, so the best design uses each for what it is good at. First, an LLM can turn messy real-world input (emails from instructors, notes like "prefers mornings" or "CS 107 where appropriate", or the free-text scheduling_notes in rooms.csv) into structured constraints and weights, which a person reviews before they go to the solver. Second, the CSP solver stays in charge of correctness: every timetable is checked by the hard-constraint engine, so a mistake by the LLM can never create a room or instructor clash. Third, an LLM can explain the result in plain language, for example why CS 107 did not get its requested room, and it can turn change requests like "move CS 341 off Fridays" into new constraints for a quick re-solve. Learned models can also help the search itself, for example by predicting enrollment from past terms (this dataset has no enrollment column), learning good variable or value orderings from earlier timetables, or suggesting starting points for local search. The important part is that the LLM proposes and the solver verifies, so the final schedule is always feasible and can be checked.