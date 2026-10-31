# Contributing to Viator

Viator runs on real hardware. A focused change, a clear explanation, and a clean working tree are
not paperwork, they make the rover easier to trust when it is far from a desk.

## Get oriented

Start with the [development setup](https://docs.trickfirerobotics.com/viator/getting-started), then
read the relevant part of the [architecture](https://docs.trickfirerobotics.com/viator/architecture).
The documentation owns environment setup, launch procedures, and package-level background, so this
guide stays focused on the contribution loop.

If your change touches a subsystem you have not worked with before, follow the message flow before
editing it. Most rover bugs are boundary bugs: a topic, service, configuration value, or CAN-facing
assumption stops lining up with the next package.

## The loop

Work from the dev container, keep the change scoped, then run the checks before you hand it off:

```bash
make format
make lint
```

`make format` applies the repository's Python formatting and safe lint fixes. `make lint` is the
read-only check: Ruff catches style and static issues, and mypy checks the typed Python surface.
Run it after formatting so its output is about the change, not whitespace.

For a change that affects hardware behaviour, say what you exercised. A short note such as
“checked on the bench with two RMD motors” is far more useful than implying a full rover test that
did not happen. Do not paper over a hardware dependency just to make a local run look green.

## Opening a pull request

Make each pull request easy to review and easy to back out.

- Keep unrelated formatting, refactors, and generated output out of a functional change.
- Explain the problem and the behaviour after the change, not just the files you touched.
- Call out hardware, ROS graph, configuration, or deployment assumptions that reviewers need to
  know.
- Include the checks you ran and any useful manual test result.
- Update the documentation when a user-facing workflow, interface, or operational expectation
  changes.

Use a short, descriptive commit subject in the imperative mood. A reader should be able to skim the
history and understand why the rover changed.

## When the docs should change

The docs are the canonical place for setup and operating instructions. Update them with the code
when a contributor or operator would otherwise learn a new command, flag, prerequisite, topic, or
recovery step by trial and error. Keep implementation detail close to the code when it only matters
to maintainers.

## Need a second set of eyes?

Open a draft pull request early when the approach is uncertain or the change crosses subsystem
boundaries. A small question before a bench session is cheaper than discovering two packages made
different assumptions after the rover is assembled.
