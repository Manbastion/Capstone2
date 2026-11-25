"""Parse Grasshopper Entwine outputs into per-iteration variable overrides.

This module deliberately has no Rhino/Grasshopper imports, so the path grouping
logic can be unit-tested outside Rhino.
"""


def entwine_iteration_overrides(names_tree, values_tree, baseline, plain_pairs):
    """Return a list of override dictionaries in Entwine input order.

    ``plain_pairs`` is ``gh_bridge.plain_pairs``. Names normally arrive as one
    list branch per Entwine input. Values may arrive as one flat list (one
    scalar per name) or as multiple branches (one per variable, allowing
    vectors). The first path index groups branches belonging to one iteration.
    """
    def grouped_branches(tree, label):
        if not hasattr(tree, "Paths") or not hasattr(tree, "Branches"):
            raise ValueError(
                "%s must receive a Grasshopper data tree. Set its access to Tree."
                % label
            )

        paths = list(tree.Paths)
        branches = list(tree.Branches)
        if len(paths) != len(branches):
            raise ValueError(
                "%s has an inconsistent number of paths and branches." % label
            )
        if not branches:
            raise ValueError(
                "%s is connected but contains no branches." % label
            )

        grouped = {}
        seen_paths = set()
        for path, branch in zip(paths, branches):
            indices = tuple(int(index) for index in path.Indices)
            if not indices:
                raise ValueError(
                    "%s contains a branch without an Entwine input path." % label
                )
            if indices[0] < 0:
                raise ValueError("%s contains a negative Entwine input index." % label)
            if indices in seen_paths:
                raise ValueError("%s contains a duplicate branch path %s." % (label, indices))
            seen_paths.add(indices)
            grouped.setdefault(indices[-1], []).append(list(branch))
        return grouped

    name_groups = grouped_branches(names_tree, "EntwinedNames")
    value_groups = grouped_branches(values_tree, "EntwinedValues")

    if set(name_groups) != set(value_groups):
        missing_values = sorted(set(name_groups) - set(value_groups))
        missing_names = sorted(set(value_groups) - set(name_groups))
        details = []
        if missing_values:
            details.append(
                "EntwinedValues is missing iteration input(s): %s"
                % ", ".join(str(i + 1) for i in missing_values)
            )
        if missing_names:
            details.append(
                "EntwinedNames is missing iteration input(s): %s"
                % ", ".join(str(i + 1) for i in missing_names)
            )
        raise ValueError("; ".join(details))

    indices = sorted(name_groups)
    expected = list(range(indices[-1] + 1))
    if indices != expected:
        missing = sorted(set(expected) - set(indices))
        raise ValueError(
            "Entwine iteration inputs must be consecutive starting at input 1. "
            "Missing input(s): %s." % ", ".join(str(i + 1) for i in missing)
        )

    overrides = []
    for iteration in indices:
        iteration_names = []
        for branch in name_groups[iteration]:
            iteration_names.extend(branch)

        if not iteration_names:
            raise ValueError("Entwine iteration %d has no variable names." % (iteration + 1))

        cleaned_names = [str(name).strip() for name in iteration_names]
        duplicates = sorted({name for name in cleaned_names if cleaned_names.count(name) > 1})
        if duplicates:
            raise ValueError(
                "Entwine iteration %d contains duplicate variable names: %s"
                % (iteration + 1, ", ".join(duplicates))
            )

        value_branches = value_groups[iteration]
        if any(len(branch) == 0 for branch in value_branches):
            raise ValueError("Entwine iteration %d contains an empty Values branch." % (iteration + 1))

        if len(value_branches) == 1:
            # One branch: either one scalar per name, or a vector for one name.
            iteration_values = value_branches[0]
        else:
            # Multiple branches: normally one branch per variable. A one-item
            # branch is scalar; a multi-item branch is a vector/matrix value.
            iteration_values = [
                branch[0] if len(branch) == 1 else branch
                for branch in value_branches
            ]

        try:
            pairs, skipped = plain_pairs(iteration_names, iteration_values)
        except Exception as error:
            raise ValueError(
                "Could not read Entwine iteration %d: %s" % (iteration + 1, error)
            )

        if skipped:
            raise ValueError(
                "Invalid variables in Entwine iteration %d: %s"
                % (iteration + 1, "; ".join(skipped))
            )
        if not pairs:
            raise ValueError("Entwine iteration %d contains no valid variables." % (iteration + 1))

        unknown = [name for name in pairs if name not in baseline]
        if unknown:
            raise ValueError(
                "Entwine iteration %d contains variables not present in the baseline "
                "Names input: %s" % (iteration + 1, ", ".join(unknown))
            )

        overrides.append(dict(pairs))

    return overrides
