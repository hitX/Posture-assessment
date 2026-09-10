# Hardware Integration and Validation Plan

## Objectives

1. Complete the Azure Kinect hardware data path, device self-check, and ground calibration.
2. Run the five-pose posture and four-view pelvis capture workflows on hardware.
3. Save and replay hardware data reliably.
4. Document hardware-versus-simulation differences and blockers.
5. Build the first real-data set and report quality-gate pass rates and failure causes.
6. Validate candidate pelvis and spine models against geometric proxy metrics.
7. Verify the complete profile to capture to analysis to result workflow.

## Baseline

- Azure Kinect Sensor and Body Tracking SDKs are installed under `sdk/` and `tools/`.
- Optional hardware dependencies are installed with `pip install -e ".[hardware]"`.
- Hardware self-check, RGB/depth capture, 32 joints, quaternions, ground calibration, quality gates, and two-second stable windows are implemented.
- The end-to-end capture path is functional and awaits formal real-data validation.
- Hardware frame-rate, resolution, timing, and full-workflow baselines remain to be recorded.

## Ten-week schedule

| Week | Focus | Deliverables |
| --- | --- | --- |
| 1 | Hardware integration and capture setup | Data path, calibration, logs, blocker list |
| 2 | Real-data validation and full workflow | First data set, quality regression, model comparison |
| 3 | Data expansion and quality tuning | 20–30 participants, threshold recommendations, failure attribution |
| 4 | Model deployment and inference | Local or containerized inference pipeline and saved outputs |
| 5 | Model versus geometric metrics | Comparison report and feasibility conclusion |
| 6 | Metric fusion and levels | Fusion algorithm, experimental rules, confidence system |
| 7 | Reporting and UI completion | Structured report view and interaction acceptance |
| 8 | Repeatability validation | ICC/MAE experiment, validation data, pass/fail decision |
| 9 | Performance and packaging | Performance report, deployment package, operations guide |
| 10 | Acceptance and handoff | Full acceptance run, test report, project summary |

## Week 1: hardware integration

- Verify the Sensor SDK, Body Tracking SDK, drivers, runtimes, and native libraries.
- Exercise the hardware `DepthCameraAdapter` path for RGB, depth, and 32-joint data.
- Establish ground and IMU calibration profiles.
- Run hardware capture through quality gates, five poses, four pelvis views, MKV/NPZ/PNG storage, and recapture archival.
- Record frame rate, resolution, capture time, and errors and compare them with simulation mode.

## Week 2: real-data validation

- Capture three to five participants across all posture and pelvis views.
- Regress single-person, distance, depth, contour, joint, stability, orientation, and Adams quality gates.
- Review pelvis metrics, confidence, and cross-view consistency on real data.
- Compare candidate model outputs with geometric and proxy metrics.
- Validate the new-profile to assessment to result workflow.

## Week 3 onward

Expand the data set under institutional ethics and privacy requirements. Tune thresholds using sensitivity analysis without marking them validated prematurely. Standardize annotation and manual review. Compare hardware and simulation behavior, including frame rate, joint jitter, depth holes, clothing artifacts, and occlusion.

Deploy two or three candidate models, measure inference time and resource use, and record failure scenarios. Design metric fusion with model confidence, depth coverage, joint completeness, cross-view consistency, and manual review. Keep unvalidated outputs marked experimental.

Complete reporting, UI acceptance, repeatability experiments, performance optimization, packaging, and final handoff according to the schedule above.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Inconsistent distance or single-person setup | Low quality-gate pass rate | Floor marks, operator guidance, pre-capture checklist |
| Hardware joint jitter or depth holes | Unstable coverage metrics | Longer stable window, recapture policy, threshold regression |
| DirectML unavailable | Lower frame rate | Keep CPU fallback and evaluate GPU acceleration |
| Clothing or occlusion sensitivity | Limited model gain | Fitted clothing, annotation standard, data augmentation |
| No pelvis ground-truth labels | No medical grading | Use manual review and inclinometer references; retain experimental status |
| SDK maintenance ended | Dependency risk | Keep an adapter interface and reserve an Orbbec-compatible path |
| Non-ASCII installation path | Native loading issues | Use the ASCII cache path documented in the README |

## Acceptance criteria

- ICC >= 0.90 for repeatability.
- Standard-angle MAE <= 2 degrees and distance MAE <= 10 mm.
- Adams inclinometer MAE <= 2 degrees with ICC >= 0.85.
- Failed validation metrics remain saved but marked experimental.
- Screening outputs never include disease probabilities, Cobb angles, or diagnoses.
