import 'dart:math' as math;

import 'package:fitahead_character/fitahead_character.dart';
import 'package:test/test.dart';

import 'manifest_test.dart' show loadManifest;

void main() {
  late CharacterPreset preset;
  late FocusCamera camera;

  setUpAll(() {
    preset = loadManifest().preset('male');
    camera = FocusCamera(preset: preset);
  });

  /// Half-angle from the camera to the edge of the framing sphere. If this
  /// stays inside the field of view in both axes, the part is fully on screen.
  double angularRadius(CameraPose pose, FocusView view) =>
      math.asin((view.framingRadius / pose.distance).clamp(-1.0, 1.0)) *
      180 /
      math.pi;

  test('every focus view fits its subject on a portrait phone', () {
    const aspect = 9 / 19.5;
    for (final view in preset.focusViews) {
      final pose = camera.poseFor(view, aspect: aspect);
      final halfVertical = pose.fovDeg / 2;
      final halfHorizontal =
          math.atan(math.tan(pose.fovDeg / 2 * math.pi / 180) * aspect) *
              180 /
              math.pi;
      final needed = angularRadius(pose, view);
      expect(needed, lessThanOrEqualTo(halfVertical + 1e-6),
          reason: '${view.id} is cropped vertically');
      expect(needed, lessThanOrEqualTo(halfHorizontal + 1e-6),
          reason: '${view.id} is cropped horizontally');
    }
  });

  test('a narrower viewport pushes the camera back', () {
    final view = preset.view('pecs')!;
    final wide = camera.distanceFor(view, aspect: 16 / 9);
    final portrait = camera.distanceFor(view, aspect: 9 / 16);
    expect(portrait, greaterThan(wide));
  });

  test(
      'viewports wider than tall do not pull the camera in past the vertical fit',
      () {
    final view = preset.view('pecs')!;
    expect(camera.distanceFor(view, aspect: 3.0),
        closeTo(camera.distanceFor(view, aspect: 1.0), 1e-9));
  });

  test('zoom moves the camera closer, proportionally', () {
    final view = preset.view('biceps')!;
    final base = camera.distanceFor(view, aspect: 1.0);
    expect(camera.distanceFor(view, aspect: 1.0, zoom: 2.0),
        closeTo(base / 2, 1e-9));
  });

  test('the camera sits at the framing distance from the target', () {
    for (final view in preset.focusViews) {
      final pose = camera.poseFor(view, aspect: 1.0);
      expect(
          pose.distance, closeTo(camera.distanceFor(view, aspect: 1.0), 1e-9));
      expect(pose.target, view.target);
    }
  });

  test('yaw 0 puts the camera in front of the character (+Z)', () {
    final chest = preset.view('pecs')!;
    expect(chest.yawDeg, 0.0);
    final pose = camera.poseFor(chest, aspect: 1.0);
    expect(pose.position.z, greaterThan(chest.target.z));
    expect(pose.position.x, closeTo(chest.target.x, 1e-9));
  });

  test('the back view looks from behind', () {
    final back = preset.view('lats')!;
    final pose = camera.poseFor(back, aspect: 1.0);
    expect(pose.position.z, lessThan(back.target.z));
  });

  test('positive pitch lifts the camera above the target', () {
    final shoulders = preset.view('delts')!;
    expect(shoulders.pitchDeg, greaterThan(0));
    final pose = camera.poseFor(shoulders, aspect: 1.0);
    expect(pose.position.y, greaterThan(shoulders.target.y));
  });

  test('a yaw offset orbits without changing the distance', () {
    final view = preset.view('pecs')!;
    final straight = camera.poseFor(view, aspect: 1.0);
    final orbited = camera.poseFor(view, aspect: 1.0, yawOffsetDeg: 40);
    expect(orbited.distance, closeTo(straight.distance, 1e-9));
    expect(orbited.position.x, greaterThan(straight.position.x));
  });

  test('an extreme pitch offset is clamped short of the pole', () {
    final view = preset.view('pecs')!;
    final pose = camera.poseFor(view, aspect: 1.0, pitchOffsetDeg: 500);
    // at the pole the camera's up vector is undefined and lookAt degenerates
    expect(pose.position.y - view.target.y, lessThan(pose.distance * 0.9999));
  });

  test('poseForId falls back rather than throwing on an unknown view', () {
    expect(() => camera.poseForId('elbows', aspect: 1.0), returnsNormally);
  });

  test('opposing muscles are framed from opposite sides', () {
    // the triceps sits behind the humerus and the hamstrings behind the femur,
    // so a front-on shot per body part would hide half the muscle groups
    for (final pair in [
      ['biceps', 'triceps'],
      ['quads', 'hams'],
      ['pecs', 'lats'],
    ]) {
      final front = camera.poseForId(pair[0], aspect: 1.0);
      final back = camera.poseForId(pair[1], aspect: 1.0);
      final frontTarget = preset.view(pair[0])!.target;
      final backTarget = preset.view(pair[1])!.target;
      expect(front.position.z - frontTarget.z, greaterThan(0),
          reason: '${pair[0]} should be seen from the front');
      expect(back.position.z - backTarget.z, lessThan(0),
          reason: '${pair[1]} should be seen from behind');
    }
  });

  test('CameraPose.lerp walks from one framing to the other', () {
    final a = camera.poseForId('full_body', aspect: 1.0);
    final b = camera.poseForId('biceps', aspect: 1.0);
    expect(CameraPose.lerp(a, b, 0.0).position, a.position);
    expect(CameraPose.lerp(a, b, 1.0).position, b.position);
    final mid = CameraPose.lerp(a, b, 0.5);
    expect(mid.target.y, closeTo((a.target.y + b.target.y) / 2, 1e-9));
  });
}
