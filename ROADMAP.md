# October delivery plan

Planning assumption: 4–6 hours per week alongside school, IELTS and applications. Review scope after the first real-data attempt. Internal portfolio freeze: October 28, 2026.

## October 4–7: First version

- Run the synthetic demo and tests locally.
- Explain what the score, threshold, usable mask and region filter do.
- Publish the first repository, with the generated-data label intact.
- Record a 30-second demo. Describe this as an image difference baseline.

## October 8–14: One real location

- Choose one pilot location and a narrow comparison question.
- Obtain two comparable images with permission to use them.
- Record provider, acquisition dates, location, resolution, processing and license in `DATA_NOTES.md`.
- Check alignment and comparable season/exposure. Exclude cloud/shadow/nodata pixels present on either date.
- If this is blocked by October 12, use a licensed public change-detection sample with documented provenance for the technical experiment; keep Kazakhstan as the proposed pilot.
- Annotate both changed and unchanged areas. Keep tuning examples separate from evaluation examples.

## October 15–21: Measure and improve

- Inspect false positives and false negatives, including stable control areas.
- Report precision, recall, F1 and IoU on held-out annotations, with the small-sample limitation stated.
- Compare one justified improvement with the original baseline, under the same evaluation conditions.
- Add ML only if there are enough suitable labelled examples and time to evaluate it meaningfully. Otherwise finish a good baseline study.

## October 22–28: Make the work reviewable

- Ask two or three people to run the app and note concrete problems.
- Fix issues, include real screenshots when permitted, and record a 60–90 second demo.
- Document results, limitations, personal contributions and next steps.
- Tag a working release and pin the repository. Confirm another person can reproduce the demo from the README.

## October 29–November 1: Application

- Keep the working release stable while completing the application.
- Describe the actual completed work; distinguish implemented features from planned ones.
- Continue the project after the deadline if the problem remains interesting.

## Scope limits for this month

The target is one small working project with traceable evidence. Automated legal judgments, Kazakhstan-wide monitoring, real-time alerts and training a large model are future work. License polygons may eventually support inspection, but a polygon match alone cannot establish legality.

## First session: 60–90 minutes

1. Run the app and tests.
2. Try threshold 0, 35 and 255; explain why the flagged mask changes.
3. Try minimum region size 1 and 500; inspect which regions disappear.
4. Compare an image to itself using the CLI.
5. Create the repository and make the first honest commit.

Keep a short experiment log: question, change, observation, next decision. Commit meaningful changes as they happen.
