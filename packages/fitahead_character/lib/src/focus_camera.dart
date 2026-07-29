import 'dart:math' as math;

import 'manifest.dart';
import 'vec3.dart';

/// A resolved camera placement, ready to hand to a renderer.
class CameraPose {
  const CameraPose({
    required this.position,
    required this.target,
    required this.fovDeg,
  });

  final Vec3 position;
  final Vec3 target;
  final double fovDeg;

  double get distance => (position - target).length;

  /// Interpolates position and target directly. Distance dips slightly on a
  /// wide swing because the path is a chord rather than an arc; for the small
  /// yaw deltas between adjacent body parts that reads as a natural ease.
  static CameraPose lerp(CameraPose a, CameraPose b, double t) => CameraPose(
        position: Vec3.lerp(a.position, b.position, t),
        target: Vec3.lerp(a.target, b.target, t),
        fovDeg: a.fovDeg + (b.fovDeg - a.fovDeg) * t,
      );

  @override
  String toString() => 'CameraPose(pos: $position, target: $target, '
      'fov: ${fovDeg.toStringAsFixed(1)})';
}

/// Turns a [FocusView] into a concrete camera placement.
///
/// The manifest ships a nominal distance for a square viewport. Phones are
/// portrait, so the horizontal field of view is the tighter constraint there:
/// framing purely on the vertical would crop the shoulders out of an arms shot.
/// [poseFor] corrects for that by widening the distance as the viewport gets
/// narrower.
class FocusCamera {
  const FocusCamera({required this.preset});

  final CharacterPreset preset;

  /// [aspect] is viewport width / height. [zoom] > 1 moves the camera closer.
  /// [yawOffsetDeg] lets the user orbit away from the canned angle without
  /// losing the framing.
  CameraPose poseFor(
    FocusView view, {
    required double aspect,
    double zoom = 1.0,
    double yawOffsetDeg = 0.0,
    double pitchOffsetDeg = 0.0,
    double? fovDeg,
  }) {
    assert(aspect > 0, 'aspect must be positive');
    assert(zoom > 0, 'zoom must be positive');

    final fov = fovDeg ?? preset.focusFovDeg;
    final distance = distanceFor(view, aspect: aspect, zoom: zoom, fovDeg: fov);

    final yaw = _radians(view.yawDeg + yawOffsetDeg);
    // clamped so an over-eager drag cannot flip the camera past the poles,
    // where lookAt has no stable up vector
    final pitch = _radians(
      (view.pitchDeg + pitchOffsetDeg).clamp(-85.0, 85.0),
    );

    final position = Vec3(
      view.target.x + distance * math.cos(pitch) * math.sin(yaw),
      view.target.y + distance * math.sin(pitch),
      view.target.z + distance * math.cos(pitch) * math.cos(yaw),
    );
    return CameraPose(position: position, target: view.target, fovDeg: fov);
  }

  /// Distance at which a sphere of [FocusView.framingRadius] fills the viewport
  /// in both axes.
  double distanceFor(
    FocusView view, {
    required double aspect,
    double zoom = 1.0,
    double? fovDeg,
  }) {
    final fov = fovDeg ?? preset.focusFovDeg;
    final halfVertical = _radians(fov) / 2;
    // horizontal half-FOV for this viewport; on a portrait phone it is the
    // tighter of the two, and framing on the vertical alone crops the sides
    final halfHorizontal = math.atan(math.tan(halfVertical) * aspect);
    final half = math.min(halfVertical, halfHorizontal);
    // sin, not tan: the framing sphere is tangent to the view frustum, so the
    // limit is the angle subtended by the sphere, not by a flat plane at its
    // centre. tan under-shoots and clips the silhouette at wide framings.
    return view.framingRadius / math.sin(half) / zoom;
  }

  /// Convenience: pose for a view id, falling back to the first view.
  CameraPose poseForId(
    String viewId, {
    required double aspect,
    double zoom = 1.0,
    double yawOffsetDeg = 0.0,
    double pitchOffsetDeg = 0.0,
  }) {
    final view = preset.view(viewId) ?? preset.focusViews.first;
    return poseFor(
      view,
      aspect: aspect,
      zoom: zoom,
      yawOffsetDeg: yawOffsetDeg,
      pitchOffsetDeg: pitchOffsetDeg,
    );
  }

  static double _radians(double degrees) => degrees * math.pi / 180.0;
}
