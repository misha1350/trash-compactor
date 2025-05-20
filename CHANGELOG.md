# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.7] - 2025-05-20
### Added
- Hard Drive check, to discourage using the program with a hard drive so as to keep the performance high (more testing with a hard drive needs to be done to evaluate performance loss)
- More extensions of poorly compressable files that are to be skipped

## [0.2.6] - 2025-03-15
### Added
- New operation modes to handle different use cases:
  - Normal mode (default): Fast compression with basic detection
  - Thorough mode (-t flag): More accurate but slower compression checks for daily/scheduled tasks
  - Branding mode (-b flag): For marking files as compressed after initial compression
- Performance improvements in file compression detection:
  - Avoiding slow "compact /a" checks in normal mode
  - Optimized file detection logic to speed up initial compression runs
- Better guidance on optimal usage patterns for different scenarios:
  - One-time compression of new directories
  - Regular scheduled compression tasks
  - Post-compression branding for Windows compatibility
- Improved command-line argument handling with mutually exclusive operation modes

### Changed
- Reduced unnecessary file checks during normal compression mode
- Made thorough checking an explicit opt-in feature for scheduled tasks
- Clarified help text and documentation for different operation modes
- Updated guidance for optimal configuration based on use case

### Fixed
- Performance bottleneck during compression checks by making thorough checks optional
- Potential reprocessing of already compressed files in daily operations

## [0.2.5] - 2025-03-11
### Added
- New `-b` flag for cleanup mode that only brands files as compressed using legacy method
- Skip main compression when using `-b` flag to avoid redundant work
- More thorough compression verification to prevent re-compression attempts
- Improved compression state detection using legacy Windows APIs
- Better handling of already compressed files to prevent unnecessary reprocessing
- Non-verbose mode now shows a dynamic spinner during compression
- Improved file path display in non-verbose mode:
    - Shows relative paths instead of absolute paths
    - Condenses deep paths with ellipses (e.g., "folder/.../subfolder/file.txt")
    - Maintains full path visibility for files near the root
- Better terminal output handling with proper line clearing

### Changed
- Separated compression and branding into distinct operations
- Improved status reporting for compression verification
- Updated help text and pro tips to include new cleanup mode functionality
- Non-verbose mode now provides better visual feedback during compression
- Improved path formatting for better readability

### Fixed
- Fixed issue where some compressed files were not properly marked in Windows
- Resolved the persistent bug causing files to be recompressed unnecessarily

## [0.2.4] - 2025-03-10
### Added
- Improved CPU detection for LZX compression with minimum threshold requirements
- New `-f` flag to force LZX compression on less capable CPUs
- "Press any key to exit" prompt after compression completes
- More specific error handling for better troubleshooting

### Fixed
- Incorrect reporting of space saved after compression
- More robust file checking with improved error handling
- Better detection of system limitations for compression

## [0.2.3] - 2024-12-04
### Added
- More file formats that are poorly compressable

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