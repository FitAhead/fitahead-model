import 'package:fitahead_character/fitahead_character.dart';
import 'package:test/test.dart';

import 'manifest_test.dart' show loadManifest;

void main() {
  late CharacterPreset preset;
  late GrowthModel model;

  setUpAll(() {
    preset = loadManifest().preset('male');
    model = GrowthModel(preset: preset);
  });

  group('GrowthCurve', () {
    const curve = GrowthCurve(halfVolume: 100);

    test('starts at zero and rises with volume', () {
      expect(curve.weightFor(const PartProgress(volume: 0)), 0.0);
      expect(curve.weightFor(const PartProgress(volume: 50)),
          lessThan(curve.weightFor(const PartProgress(volume: 100))));
    });

    test('reaches half weight at halfVolume', () {
      expect(
          curve.weightFor(const PartProgress(volume: 100)), closeTo(0.5, 1e-9));
    });

    test('saturates instead of overshooting', () {
      final huge = curve.weightFor(const PartProgress(volume: 1e6));
      expect(huge, lessThanOrEqualTo(1.0));
      expect(huge, closeTo(1.0, 1e-6));
    });

    test('front-loads progress: the first sessions move more than the last',
        () {
      final early = curve.weightFor(const PartProgress(volume: 50)) -
          curve.weightFor(const PartProgress(volume: 0));
      final late = curve.weightFor(const PartProgress(volume: 350)) -
          curve.weightFor(const PartProgress(volume: 300));
      expect(early, greaterThan(late * 4));
    });

    test('volumeForWeight inverts weightFor', () {
      for (final w in [0.1, 0.25, 0.5, 0.8]) {
        final v = curve.volumeForWeight(w);
        expect(curve.weightFor(PartProgress(volume: v)), closeTo(w, 1e-9));
      }
      expect(curve.volumeForWeight(1.0), double.infinity);
    });

    test('detraining shrinks effective volume but never below the floor', () {
      const trained = PartProgress(volume: 200);
      const rested = PartProgress(
        volume: 200,
        sinceLastSession: Duration(days: 60),
      );
      expect(curve.effectiveVolume(rested),
          lessThan(curve.effectiveVolume(trained)));

      const forgotten = PartProgress(
        volume: 200,
        sinceLastSession: Duration(days: 3650),
      );
      // muscle memory: ten years off still leaves the retained share
      expect(curve.effectiveVolume(forgotten),
          closeTo(200 * curve.retainedFloor, 1e-6));
    });

    test('a short break barely moves the needle', () {
      const fresh = PartProgress(volume: 200);
      const weekOff = PartProgress(
        volume: 200,
        sinceLastSession: Duration(days: 7),
      );
      expect(curve.weightFor(weekOff), closeTo(curve.weightFor(fresh), 0.05));
    });
  });

  group('GrowthModel', () {
    test('an untrained body is all zeros', () {
      final state = model.stateFor(const TrainingProgress());
      for (final m in preset.morphTargets) {
        expect(state[m.name], 0.0, reason: m.name);
      }
    });

    test('training one group grows that group', () {
      final state = model.stateFor(const TrainingProgress(
        parts: {'arms': PartProgress(volume: 120)},
      ));
      expect(state['arms'], greaterThan(0.4));
      expect(state['thighs'], 0.0);
      expect(state['chest'], 0.0);
    });

    test('bulk trails the mean of the trained groups', () {
      final state = model.stateFor(const TrainingProgress(
        parts: {'arms': PartProgress(volume: 1e6)},
      ));
      // one group maxed out of eight trainable ones
      expect(state[GrowthMorphs.bulk], greaterThan(0.0));
      expect(state[GrowthMorphs.bulk], lessThan(state['arms']));
    });

    test('training everything approaches a fully grown body', () {
      final volumes = {
        for (final m in preset.morphTargets)
          if (!m.isRegression && m.name != GrowthMorphs.bulk)
            m.name: const PartProgress(volume: 1e6),
      };
      final state = model.stateFor(TrainingProgress(parts: volumes));
      expect(state.overall(preset), closeTo(1.0, 1e-5));
      expect(state[GrowthMorphs.bulk], closeTo(model.bulkShare, 1e-5));
    });

    test('belly comes from body composition, not from training', () {
      final trained = model.stateFor(const TrainingProgress(
        parts: {'abs': PartProgress(volume: 1e6)},
        bellyLevel: 0.7,
      ));
      expect(trained[GrowthMorphs.belly], closeTo(0.7, 1e-9));
    });

    test('unknown morph names in progress are ignored, not crashed on', () {
      final state = model.stateFor(const TrainingProgress(
        parts: {'tail': PartProgress(volume: 500)},
      ));
      expect(state.overall(preset), 0.0);
    });

    test('withSession accumulates and resets the idle clock', () {
      const start = TrainingProgress(
        parts: {
          'chest':
              PartProgress(volume: 40, sinceLastSession: Duration(days: 30))
        },
      );
      final after = start.withSession('chest', 10);
      expect(after.parts['chest']!.volume, 50);
      expect(after.parts['chest']!.sinceLastSession, Duration.zero);
    });

    group('stages', () {
      test('spans 0 to stageCount - 1', () {
        expect(model.stageOf('arms', 0.0), 0);
        expect(model.stageOf('arms', 1.0), model.stageCount - 1);
        expect(model.stageOf('arms', 0.5),
            inInclusiveRange(0, model.stageCount - 1));
      });

      test('never decreases as weight rises', () {
        var previous = 0;
        for (var w = 0.0; w <= 1.0; w += 0.01) {
          final stage = model.stageOf('arms', w);
          expect(stage, greaterThanOrEqualTo(previous));
          previous = stage;
        }
      });

      test('volumeToNextStage is positive below the cap and null at the top',
          () {
        const early = PartProgress(volume: 5);
        expect(model.volumeToNextStage('arms', early), greaterThan(0));
        const maxed = PartProgress(volume: 1e6);
        expect(model.volumeToNextStage('arms', maxed), isNull);
      });

      test('adding exactly volumeToNextStage reaches the next stage', () {
        const progress = PartProgress(volume: 30);
        final stage =
            model.stageOf('arms', model.curveFor('arms').weightFor(progress));
        final needed = model.volumeToNextStage('arms', progress)!;
        final advanced = PartProgress(volume: progress.volume + needed);
        expect(
          model.stageOf('arms', model.curveFor('arms').weightFor(advanced)),
          stage + 1,
        );
      });

      test('stageProgress stays within 0..1', () {
        for (final v in [0.0, 1.0, 25.0, 120.0, 400.0, 1e6]) {
          final p = model.stageProgress('arms', PartProgress(volume: v));
          expect(p, inInclusiveRange(0.0, 1.0), reason: 'volume $v');
        }
      });
    });

    test('per-group curves override the default', () {
      final tuned = GrowthModel(
        preset: preset,
        curves: const {'calves': GrowthCurve(halfVolume: 400)},
      );
      const same = TrainingProgress(parts: {
        'calves': PartProgress(volume: 120),
        'arms': PartProgress(volume: 120),
      });
      final state = tuned.stateFor(same);
      expect(state['calves'], lessThan(state['arms']),
          reason: 'stubborn calves should need more volume for the same look');
    });
  });

  group('BodyState', () {
    test('clamps weights into 0..1', () {
      final state = BodyState({'chest': 2.5, 'arms': -1.0});
      expect(state['chest'], 1.0);
      expect(state['arms'], 0.0);
    });

    test('unknown morphs read as zero', () {
      expect(BodyState(const {})['nope'], 0.0);
    });

    test('influences follow GLB morph order', () {
      final state = BodyState({'chest': 0.5});
      final influences = state.influences(preset);
      expect(influences, hasLength(preset.morphTargets.length));
      expect(influences[preset.morph('chest')!.index], 0.5);
    });

    test('lerp moves from one body to the other', () {
      final a = BodyState.rest(preset);
      final b = BodyState({'chest': 1.0});
      expect(BodyState.lerp(a, b, 0.0)['chest'], 0.0);
      expect(BodyState.lerp(a, b, 0.5)['chest'], closeTo(0.5, 1e-9));
      expect(BodyState.lerp(a, b, 1.0)['chest'], 1.0);
    });

    test('gainsOver reports what grew, biggest first', () {
      final before = BodyState({'chest': 0.1, 'arms': 0.1, 'calves': 0.5});
      final after = BodyState({'chest': 0.2, 'arms': 0.5, 'calves': 0.5});
      expect(after.gainsOver(before), ['arms', 'chest']);
    });

    test('overall ignores bulk and belly', () {
      final state =
          BodyState({GrowthMorphs.bulk: 1.0, GrowthMorphs.belly: 1.0});
      expect(state.overall(preset), 0.0);
    });
  });
}
