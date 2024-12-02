# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2024-12-03
### Added
- Toggling LZX compression on/off with the `-x` flag - useful when your CPU is very slow or old (Intel Atom, Intel Celeron)
- Flag stacking
- A To-Do list of improvements for future releases (because I will not be making any new improvements any time soon)

## [0.2.1] - 2024-12-02
### Added
- CPU capability detection for optimal compression settings
- User prompt to optionally enable LZX on slower systems with dual-core CPUs
- Display of physical cores and logical threads count

### Changed
- XPRESS16K is now used by default on lower-end systems instead of LZX
- Improved system responsiveness on dual-core systems

## [0.2.0] - 2024-12-01
### Added
- A splash screen
- Path sanitizing to handle various input formats
- Unicode support for file paths with non-ASCII characters
- Significant speed improvements in file compression checks

### Changed
- Improved logging format for better readability
- Enhanced compression summary to include already compressed files

### Fixed
- Correctly identify and skip already compressed files
- Handle exceptions more gracefully during file size checks

### Known issues
Some files are erroneously reported as being compressed, when they have already been compressed before. Even though they are not being compressed again, it must be checked 

### To-Do
The app has to sense how many cores there are and run with lower priority, so as not to impact the performance of other apps when the compression is running.

## [0.1.0] - 2024-11-30
### Added
- Initial release with basic file compression functionality.
- Smart algorithm selection based on file size.
- Detailed compression statistics.