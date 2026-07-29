/// Engine-agnostic domain model for the FitAhead 3D character.
///
/// Three pieces, all independent of how the character is actually drawn:
///
/// * [CharacterManifest] — what the generator produced: presets, joints, morph
///   targets, and canned camera framings for each body part.
/// * [GrowthModel] — training volume in, [BodyState] morph weights out.
/// * [FocusCamera] — a body part in, a [CameraPose] out.
///
/// A renderer package binds these to a specific 3D engine; nothing here imports
/// Flutter, so all of it is testable on the Dart VM.
library;

export 'src/body_state.dart';
export 'src/focus_camera.dart';
export 'src/growth.dart';
export 'src/manifest.dart';
export 'src/vec3.dart';
