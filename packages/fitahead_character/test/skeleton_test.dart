import 'dart:math' as math;

import 'package:fitahead_character/fitahead_character.dart';
import 'package:test/test.dart';

import 'manifest_test.dart' show loadManifest;

/// Anatomical invariants of the rig and the mesh.
///
/// Every test here corresponds to something that was silently wrong at some
/// point and that no render revealed: the figure stood taller than its stated
/// height, the hip joint sat at the crotch instead of the femoral head, and the
/// arms hung vertically so nothing could deform at the shoulder.
void main() {
  late CharacterManifest manifest;

  setUpAll(() => manifest = loadManifest());

  double lengthBetween(CharacterPreset p, String a, String b) {
    final ja = p.joints.firstWhere((j) => j.name == a).rest;
    final jb = p.joints.firstWhere((j) => j.name == b).rest;
    return (jb - ja).length;
  }

  test('the figure is exactly as tall as it says it is', () {
    for (final preset in manifest.presets.values) {
      final measured = preset.stats.measuredHeight;
      expect(measured, closeTo(preset.height, 0.003),
          reason: '${preset.id}: stated ${preset.height}, mesh $measured. '
              'Deriving the head upward from the neck instead of down from the '
              'vertex once made this 3.6% over.');
    }
  });

  test('the character stands on the ground, not above it', () {
    for (final preset in manifest.presets.values) {
      // the shoe sole is the contact surface, so a millimetre below zero is the
      // sole's own thickness rather than a floating character
      expect(preset.stats.boundsMin[1], closeTo(0.0, 0.003),
          reason: '${preset.id}: sole at ${preset.stats.boundsMin[1]}');
    }
  });

  test('the mesh extends beyond both wrist joints to include hands', () {
    for (final preset in manifest.presets.values) {
      final leftWrist =
          preset.joints.firstWhere((j) => j.name == 'Hand_L').rest;
      final rightWrist =
          preset.joints.firstWhere((j) => j.name == 'Hand_R').rest;
      final minimumExtension = preset.height * 0.045;

      expect(preset.stats.boundsMax[0] - leftWrist.x,
          greaterThan(minimumExtension),
          reason: '${preset.id}: left arm ends at the wrist');
      expect(rightWrist.x - preset.stats.boundsMin[0],
          greaterThan(minimumExtension),
          reason: '${preset.id}: right arm ends at the wrist');
    }
  });

  group('A-pose', () {
    test('the arms are abducted, not hanging', () {
      for (final preset in manifest.presets.values) {
        final shoulder =
            preset.joints.firstWhere((j) => j.name == 'UpperArm_L').rest;
        final elbow =
            preset.joints.firstWhere((j) => j.name == 'Forearm_L').rest;
        final down = shoulder.y - elbow.y;
        final out = elbow.x - shoulder.x;
        final abduction = math.atan2(out, down) * 180 / math.pi;
        expect(abduction, inInclusiveRange(30.0, 65.0),
            reason:
                '${preset.id}: abduction ${abduction.toStringAsFixed(1)} deg. '
                'Arms glued to the ribs hide the lats and leave skinning '
                'nowhere to deform.');
      }
    });

    test('left and right are mirrored', () {
      for (final preset in manifest.presets.values) {
        for (final base in [
          'Shoulder',
          'UpperArm',
          'Forearm',
          'Hand',
          'Thigh',
          'Shin',
          'Foot',
          'Toe'
        ]) {
          final l = preset.joints.firstWhere((j) => j.name == '${base}_L').rest;
          final r = preset.joints.firstWhere((j) => j.name == '${base}_R').rest;
          expect(r.x, closeTo(-l.x, 1e-6), reason: base);
          expect(r.y, closeTo(l.y, 1e-6), reason: base);
          expect(r.z, closeTo(l.z, 1e-6), reason: base);
        }
      }
    });
  });

  group('segment lengths', () {
    test('limb bones are the right length for the stature', () {
      // fractions of stature: Drillis & Contini segment lengths
      const expected = {
        'upper_arm': 0.188, // acromion -> radiale
        'forearm': 0.145, // radiale -> stylion
        'thigh': 0.245, // femur
        'shin': 0.246, // tibia
      };
      for (final preset in manifest.presets.values) {
        final h = preset.height;
        expect(lengthBetween(preset, 'UpperArm_L', 'Forearm_L'),
            closeTo(expected['upper_arm']! * h, 0.004));
        expect(lengthBetween(preset, 'Forearm_L', 'Hand_L'),
            closeTo(expected['forearm']! * h, 0.004));
        expect(lengthBetween(preset, 'Thigh_L', 'Shin_L'),
            closeTo(expected['thigh']! * h, 0.004));
        expect(lengthBetween(preset, 'Shin_L', 'Foot_L'),
            closeTo(expected['shin']! * h, 0.004));
      }
    });

    test('the hip joint is the femoral head, not the crotch', () {
      for (final preset in manifest.presets.values) {
        final hip = preset.joints.firstWhere((j) => j.name == 'Thigh_L').rest;
        // trochanter sits at 0.530H; the crotch is at 0.485H, and rooting the
        // thigh there costs a fifth of the femur
        expect(hip.y / preset.height, closeTo(0.530, 0.012),
            reason: '${preset.id}: hip at ${hip.y / preset.height}H');
      }
    });
  });

  test('the skeleton is identical between body types', () {
    // Bone does not respond to training, which is the whole reason one rig can
    // serve every archetype.
    final male = manifest.preset('male');
    final female = manifest.preset('female');
    expect(male.joints.map((j) => j.name), female.joints.map((j) => j.name));
    expect(male.joints.map((j) => j.humanoid),
        female.joints.map((j) => j.humanoid));
  });

  group('humanoid bone mapping', () {
    test('every humanoid role resolves to a joint that exists', () {
      for (final preset in manifest.presets.values) {
        final names = {for (final j in preset.joints) j.name};
        preset.humanoidBones.forEach((role, node) {
          expect(names, contains(node), reason: '$role -> $node');
        });
      }
    });

    test('covers the bones a humanoid animation needs', () {
      for (final preset in manifest.presets.values) {
        expect(
          preset.humanoidBones.keys,
          containsAll(<String>[
            'hips',
            'spine',
            'chest',
            'upperChest',
            'neck',
            'head',
            'leftUpperArm',
            'leftLowerArm',
            'leftHand',
            'rightUpperArm',
            'rightLowerArm',
            'rightHand',
            'leftUpperLeg',
            'leftLowerLeg',
            'leftFoot',
            'rightUpperLeg',
            'rightLowerLeg',
            'rightFoot',
          ]),
        );
      }
    });

    test('each joint agrees with the reverse mapping', () {
      for (final preset in manifest.presets.values) {
        for (final joint in preset.joints) {
          if (joint.humanoid == null) continue;
          expect(preset.humanoidBones[joint.humanoid], joint.name);
        }
      }
    });
  });
}
