# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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