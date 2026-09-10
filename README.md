# Posture Assessment System

A Windows desktop application built with Python 3.12, PySide6, and SQLite. It provides patient profiles, five-pose Azure Kinect posture capture, four-view pelvis screening, hard quality gates, surface point-cloud proxy metrics, manual review, and local result persistence.

## Run

Dependencies are installed in `.venv`:

```powershell
& ".\.venv\Scripts\python.exe" .\run.py
```

The default login is `admin` / `admin123`.

The first run creates the SQLite database, raw assessment data, calibration profiles, threshold configuration, export directory, and import logs under `data/`.

## Features

- Login, password visibility, and credential validation.
- `DongleAdapter` security-dongle interface with a `MockDongleAdapter` implementation.
- Patient search by ID, name, and mobile number.
- Create, edit, view, and archive patient profiles.
- Automatic age calculation and validation for IDs, mobile numbers, and email addresses.
- Incomplete imported profiles are allowed, but mobile, height, weight, and address are required before capture.
- Patient assessment history and new assessment handoff from the profile list.
- XLSX/CSV batch import with field mapping, duplicate strategies, error details, and audit records.
- XLSX/CSV/JSON export with anonymization, ZIP packaging, manifests, and SHA-256 checksums.
- Navigation placeholders for future gait, spine, joint, foot, and reporting modules.

## Posture assessment

- `DepthCameraAdapter` supports Azure Kinect, MKV/NPZ replay, and deterministic simulation.
- Camera and body tracking run in a separate `spawn` worker process.
- Front, left-side, back, right-side, and Adams forward-bend capture with per-pose recapture.
- Two-second hard quality gate covering body count, distance, depth and contour coverage, joints, stability, orientation, and Adams angle.
- Optional Open3D filtering and RANSAC; NumPy replay remains available for CI and camera-free development.
- Geometry, side-surface spline, and Adams layered cross-section algorithms. Surface curvature, lateral deviation, and rotation outputs are explicitly proxy values.
- Confidence combines depth coverage, joint completeness, stability, fit residuals, and cross-pose consistency. Results below 70% confidence do not receive a screening conclusion.
- Initial thresholds are stored in `data/posture_thresholds.json` with `validated=false`; levels are therefore experimental and pending validation.
- Manual ruler, line, angle, zoom, mirror, undo, and redo annotations are stored separately in `posture_reviews` and never overwrite automatic points.
- `analysis_ready(session_id)` exposes the structured result package; PDF generation is not included in this version.

## Pelvis screening

- One Azure Kinect captures front, left-side, back, and right-side views.
- `FrameBundle` and NPZ replay support optional 32-joint `wxyz` quaternions.
- Warm-up checks use pelvis and hip position RMS plus joint orientation spread.
- Output includes hip-height difference, coronal hip-axis tilt proxy, pelvis shift relative to the support base, model pelvis pitch and yaw proxies, and posterior hip/gluteal surface symmetry proxy.
- Paired views are confidence-weighted and angles use circular averaging. Cross-view disagreement is retained and marked for manual review instead of being forced into an average.
- Results are experimental proxy values, not clinical ASIS-PSIS angles or medical grades.

## Camera backends

The default `auto` backend uses Azure Kinect when the Python bindings and Microsoft runtime are available; otherwise it enters clearly marked simulation mode.

```powershell
$env:POSTURE_CAMERA_BACKEND = 'mock'
$env:POSTURE_MOCK_SCENARIO = 'multiple_bodies'
$env:POSTURE_CAMERA_BACKEND = 'azure_kinect'
$env:POSTURE_CAMERA_BACKEND = 'replay'
$env:POSTURE_REPLAY_ROOT = 'D:\Posture-assessment-system\data\assessments\AS...'
```

Supported simulation scenarios include `multiple_bodies`, `too_far`, `occluded`, `depth_holes`, `unstable`, `wrong_orientation`, `bad_adams`, and `garment_artifact`.

## Azure Kinect hardware

The project does not bundle Microsoft's closed-source Body Tracking binaries. The deployment machine must separately install the Azure Kinect Sensor SDK 1.4.x, Body Tracking SDK 1.1.x, and optional hardware dependencies:

```powershell
& .\.venv\Scripts\python.exe -m pip install -e ".[hardware]"
```

See `LICENSE.txt` and `ThirdPartyNotices.txt` for the applicable SDK and third-party terms.

## Scope and validation

This module supports non-diagnostic posture screening. It does not output disease probabilities, Cobb angles, or diagnoses. All thresholds remain experimental until local validation with 20–30 participants and at least three repeated captures per participant.

Targets are ICC >= 0.90, standard-angle MAE <= 2 degrees, distance MAE <= 10 mm, and Adams inclinometer MAE <= 2 degrees with ICC >= 0.85.

## Tests

```powershell
& .\test.ps1
```

The test script runs pytest offscreen, uses reduced password-derivation iterations, and places temporary test data under `tmp/`.
