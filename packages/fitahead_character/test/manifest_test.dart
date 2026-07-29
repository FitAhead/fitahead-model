import 'dart:io';

import 'package:fitahead_character/fitahead_character.dart';
import 'package:test/test.dart';

/// Tests run against the real generated manifest rather than a fixture, so a
/// change to `tools/gen_character.py` that breaks the contract fails here.
CharacterManifest loadManifest() => CharacterManifest.parse(
      File('../../assets/models/character_manifest.json').readAsStringSync(),
    );

void main() {
  late CharacterManifest manifest;

  setUpAll(() => manifest = loadManifest());

  test('ships a male and a female preset', () {
    expect(manifest.presets.keys, containsAll(<String>['male', 'female']));
    expect(manifest.preset('male').sex, 'male');
    expect(manifest.preset('female').sex, 'female');
  });

  test('unknown preset names fail loudly', () {
    expect(() => manifest.preset('nonbinary'), throwsArgumentError);
  });

  test('presets differ in silhouette, not just in name', () {
    final male = manifest.preset('male');
    final female = manifest.preset('female');
    expect(male.height, greaterThan(female.height));
    expect(male.file, isNot(female.file));
  });

  group('joints', () {
    test('indices match position, and every parent resolves', () {
      for (final preset in manifest.presets.values) {
        final names = {for (final j in preset.joints) j.name};
        for (var i = 0; i < preset.joints.length; i++) {
          expect(preset.joints[i].index, i,
              reason: '${preset.id}: joint index must equal its position, '
                  'because that is what skin.joints uses');
          final parent = preset.joints[i].parent;
          if (parent != null) expect(names, contains(parent));
        }
      }
    });

    test('exactly one root, and it is Root', () {
      for (final preset in manifest.presets.values) {
        final roots = preset.joints.where((j) => j.parent == null).toList();
        expect(roots, hasLength(1));
        expect(roots.single.name, 'Root');
      }
    });

    test('covers the parts the app needs to address', () {
      for (final preset in manifest.presets.values) {
        final names = {for (final j in preset.joints) j.name};
        expect(
          names,
          containsAll(<String>[
            'Hips',
            'Spine',
            'Chest',
            'Neck',
            'Head',
            'UpperArm_L',
            'UpperArm_R',
            'Forearm_L',
            'Forearm_R',
            'Thigh_L',
            'Thigh_R',
            'Shin_L',
            'Shin_R',
          ]),
        );
      }
    });
  });

  group('morph targets', () {
    test('indices match position — renderers index influences positionally',
        () {
      for (final preset in manifest.presets.values) {
        for (var i = 0; i < preset.morphTargets.length; i++) {
          expect(preset.morphTargets[i].index, i);
        }
      }
    });

    test('every muscle group is present and labelled in both languages', () {
      for (final preset in manifest.presets.values) {
        expect(
          preset.morphNames,
          containsAll(<String>[
            'bulk',
            'chest',
            'back',
            'shoulders',
            'arms',
            'abs',
            'glutes',
            'thighs',
            'calves',
            'belly',
          ]),
        );
        for (final m in preset.morphTargets) {
          expect(m.labelKo, isNotEmpty,
              reason: '${m.name} has no Korean label');
          expect(m.labelEn, isNotEmpty);
          expect(m.maxDisplacement, greaterThan(0));
        }
      }
    });

    test('belly is the only regression shape', () {
      for (final preset in manifest.presets.values) {
        final regressions =
            preset.morphTargets.where((m) => m.isRegression).map((m) => m.name);
        expect(regressions, ['belly']);
      }
    });

    test('both presets expose the same morphs in the same order', () {
      expect(manifest.preset('male').morphNames,
          manifest.preset('female').morphNames);
    });
  });

  group('focus views', () {
    test('every trainable view points at a real morph', () {
      for (final preset in manifest.presets.values) {
        for (final view in preset.trainableViews) {
          expect(preset.morph(view.morph!), isNotNull,
              reason: 'view ${view.id} references unknown morph ${view.morph}');
        }
      }
    });

    test('covers whole-body framings plus every trainable group', () {
      for (final preset in manifest.presets.values) {
        final ids = {for (final v in preset.focusViews) v.id};
        expect(ids, containsAll(<String>['full_body', 'upper_body', 'face']));
        final trainable = {for (final v in preset.trainableViews) v.morph};
        final growable = {
          for (final m in preset.morphTargets)
            if (!m.isRegression && m.name != GrowthMorphs.bulk) m.name,
        };
        expect(trainable, growable,
            reason: 'every growable group needs a camera to show it off');
      }
    });

    test('targets sit inside the body, and framings are positive', () {
      for (final preset in manifest.presets.values) {
        for (final view in preset.focusViews) {
          expect(view.target.y, inInclusiveRange(0.0, preset.height));
          expect(view.framingRadius, greaterThan(0));
          expect(view.distance, greaterThan(0));
        }
      }
    });

    test('the full body view frames the whole body', () {
      for (final preset in manifest.presets.values) {
        final full = preset.view('full_body')!;
        expect(full.framingRadius * 2, greaterThanOrEqualTo(preset.height),
            reason: 'full_body must fit the character head to toe');
      }
    });
  });

  test('face slot names a mesh the preset actually ships', () {
    for (final preset in manifest.presets.values) {
      expect(preset.face.uvLayout, 'disc-inscribed-in-square');
      expect(preset.face.defaultTexture, manifest.faceTexture);
    }
  });

  test('referenced asset files exist next to the manifest', () {
    for (final preset in manifest.presets.values) {
      expect(File('../../assets/models/${preset.file}').existsSync(), isTrue);
    }
    expect(File('../../assets/models/${manifest.faceTexture}').existsSync(),
        isTrue);
  });
}
