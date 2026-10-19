
import random
import time

from constraints_check import (
    count_conflicts,
    is_consistent,
    soft_penalty,
    score_schedule,
    value_cost,
)


def min_conflicts(data, start=None, max_steps=3000, seed=42, time_limit=15):
    # try to fix hard conflicts if backtracking doesn't find a solution
    rng = random.Random(seed)
    assignment = dict(start) if start else {}

    for course_id in data.course_ids:
        if course_id not in assignment and data.domains[course_id]:
            assignment[course_id] = rng.choice(data.domains[course_id])

    start_time = time.time()

    for _ in range(max_steps):
        conflicted = [
            course_id
            for course_id in assignment
            if count_conflicts(
                course_id, assignment[course_id], assignment, data
            ) > 0
        ]

        if not conflicted:
            return assignment, True

        if time.time() - start_time > time_limit:
            break

        course_id = rng.choice(conflicted)
        values = data.domains[course_id]

        # limit the number of values to check for large domains
        if len(values) > 300:
            values = rng.sample(values, 300)

        best_value = None
        fewest_conflicts = None

        for value in values:
            conflicts = count_conflicts(course_id, value, assignment, data)

            if (
                fewest_conflicts is None
                or conflicts < fewest_conflicts
                or (
                    conflicts == fewest_conflicts
                    and rng.random() < 0.5
                )
            ):
                best_value = value
                fewest_conflicts = conflicts

        if best_value is not None:
            assignment[course_id] = best_value

    return assignment, False


def min_conflicts_soft(
    data, assignment, max_steps=3000, seed=42, time_limit=20, patience=400
):
    # improve the schedule while keeping the hard constraints satisfied
    rng = random.Random(seed)
    current = dict(assignment)

    current_penalty, _ = soft_penalty(current, data)
    best_schedule = dict(current)
    best_penalty = current_penalty

    start_time = time.time()
    steps_without_improvement = 0
    steps = 0

    for _ in range(max_steps):
        if (
            time.time() - start_time > time_limit
            or steps_without_improvement >= patience
        ):
            break

        _, blame = score_schedule(current, data)

        conflicted = [
            course_id
            for course_id in data.course_ids
            if blame.get(course_id, 0) > 0
            and len(data.domains[course_id]) > 1
        ]

        if not conflicted:
            break

        steps += 1
        course_id = rng.choice(conflicted)
        old_value = current[course_id]

        # collect values that don't create hard conflicts
        options = []

        for value in data.domains[course_id]:
            if value != old_value and is_consistent(
                course_id, value, current, data
            ):
                options.append((value_cost(course_id, value, data), value))

        if not options:
            steps_without_improvement += 1
            continue

        # check the cheapest values and a few other options
        lowest_cost = min(cost for cost, _ in options)
        cheapest = [
            value for cost, value in options if cost == lowest_cost
        ]
        others = [
            value for cost, value in options if cost > lowest_cost
        ]

        if len(cheapest) > 30:
            cheapest = rng.sample(cheapest, 30)

        if len(others) > 10:
            others = rng.sample(others, 10)

        candidates = cheapest + others + [old_value]

        best_value = old_value
        best_value_penalty = None

        for value in candidates:
            current[course_id] = value
            penalty, _ = soft_penalty(current, data)

            # randomly choose between equal penalties
            if (
                best_value_penalty is None
                or penalty < best_value_penalty
                or (
                    penalty == best_value_penalty
                    and rng.random() < 0.5
                )
            ):
                best_value = value
                best_value_penalty = penalty

        current[course_id] = best_value
        current_penalty = best_value_penalty

        if current_penalty < best_penalty:
            best_schedule = dict(current)
            best_penalty = current_penalty
            steps_without_improvement = 0
        else:
            steps_without_improvement += 1

    print("Min-conflicts steps =", steps)
    return best_schedule, best_penalty
