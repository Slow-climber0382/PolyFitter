# PolyFitter

[Polski — Przeczytaj mnie](PRZECZYTAJ_MNIE.md)

Open-source, browser-based tools for fitting 3D armor and props to body measurements.
PolyFitter is an early development release (0.6.3), formerly named Meshavon and ForgeFit.

## Use the app

The intended GitHub Pages address is https://slow-climber0382.github.io/PolyFitter/.
It becomes available after the repository owner enables Pages and a deployment succeeds.
No installation, account, backend, or model upload service is required to use the app.
Models and measurements are processed in your browser. Save projects regularly: closing
or refreshing the tab discards unsaved work. Downloads are controlled by your browser.
The current interface is Polish; English and further translations are planned.

## Available now

- Binary/ASCII STL import with explicit mm/cm/inch selection and mesh diagnostics.
- Adjustable neutral, male and female mannequins; basic/detailed measurements and poses.
- Preliminary uniform-scale fitting for helmets, chest plates and two shin-guard styles.
- Manual scale, independent XYZ, rotation, position, orientation shortcuts and nudges.
- Approximate collision, fit-color and helmet insertion checks; optional top padding.
- Multi-part projects and helmet assemblies with shared transforms.
- Undo/redo (40 changes), including measurements, transforms and part import/removal.
- Project download/reopen, including legacy `.meshavon` and `.forgefit` projects; new files use `.polyfitter`.
- STL export in millimeters, and experimental capped planar splitting for configurable printer X/Y/Z dimensions with a total allowance per axis. Printer settings persist in projects and support undo/redo. Scene Y maps to printer Z; parts are not automatically rotated or packed.

Use left drag to orbit, right drag to pan and the wheel to zoom. Six standard views,
reset and framing controls are available. Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z operate on
project history outside text inputs; inputs retain their native text undo behavior.

## Limitations

Automatic fitting is an estimate, not anatomical recognition. Set model orientation
before fitting and inspect the eyes, chin, nose and shell from multiple directions.
A collision-free final position does not guarantee that a helmet can be put on.
Real test helmets still fail the insertion check; some shin guards produce rejected
oversized proposals. The mannequin is approximate and does not reproduce every
measurement independently. The scene displays the active part or helmet kit, not
all independent parts simultaneously. The included helmet is a procedural demo.

Limits: 1 million triangles per STL; 2 million triangles and 150 MB per project.
Large meshes can pause the interface during collision reporting. Desktop-class browsers
with WebGL and module workers are required. No claim is made about physical comfort,
visibility or print readiness. Firefox, Safari and mobile compatibility need further testing.

## Run and develop

Requires Node.js 22.12 or newer. No npm dependencies are needed.

```sh
npm test
npm run build
npm start
```

Open http://127.0.0.1:8080. Do not open `index.html` using `file://`.
The static `dist/` directory can be hosted under a repository subpath; all assets use
relative URLs. The build does not include Electron or downloaded user STL files.

## Roadmap

1. Reliable helmet alignment, improved body fitting, named measurement profiles,
   OBJ/3MF and localization.
2. Papercraft patterns from fitted models.
3. Painting masks and stencils.
4. Further print preparation and mold-making tools.

These are plans, not existing features.

## Contributions and review

Fork the repository and submit a pull request. Explain the problem, exact changes,
tests and remaining limitations. Read [CONTRIBUTING.md](CONTRIBUTING.md).
Official changes require maintainer review; contributors cannot approve their own PR.
CODEOWNERS and CI are included, but enforcement requires the owner to enable the
branch settings in [MAINTAINERS.md](MAINTAINERS.md). Documentation alone does not enforce reviews.

## License and forks

Application code is licensed under [Apache License 2.0](LICENSE). You may modify,
distribute and publish your own version, including commercially. Preserve the applicable
copyright, license and attribution notices, include the relevant [NOTICE](NOTICE)
information, and prominently mark files you modify, as required by section 4.
We ask forks to provide a concrete change summary in their README or CHANGELOG;
Apache 2.0 requires modified-file notices but does not require a detailed public changelog.
It does not require forks to publish their source or obtain upstream approval.

Original project: https://github.com/Slow-climber0382/PolyFitter

MakeHuman mesh/rig/morph assets remain CC0; Earcut remains ISC. See [ASSETS.md](ASSETS.md).
Earlier ForgeFit copies distributed under MIT retain their original license.
