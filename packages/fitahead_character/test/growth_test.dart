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
        parts: {'biceps': PartProgress(volume: 120)},
      ));
      expect(state['biceps'], greaterThan(0.4));
      expect(state['quads'], 0.0);
      expect(state['pecs'], 0.0);
    });

    test('bulk trails the mean of the trained groups', () {
      final state = model.stateFor(const TrainingProgress(
        parts: {'biceps': PartProgress(volume: 1e6)},
      ));
      // one group maxed out of eight trainable ones
      expect(state[GrowthMorphs.bulk], greaterThan(0.0));
      expect(state[GrowthMorphs.bulk], lessThan(state['biceps']));
    });

    test('training everything approaches a fully grown body', () {
      final volumes = {
        for (final m in preset.muscleGroups)
          m.name: const PartProgress(volume: 1e6),
      };
      final state = model.stateFor(TrainingProgress(parts: volumes));
      expect(state.overall(preset), closeTo(1.0, 1e-5));
      expect(state[GrowthMorphs.bulk], closeTo(model.bulkShare, 1e-5));
    });

    test('fat comes from body composition and splits by sex-typical pattern',
        () {
      final state = model.stateFor(const TrainingProgress(fatLevel: 0.7));
      expect(state[GrowthMorphs.fatAndroid],
          closeTo(0.7 * preset.fatSplit.android, 1e-9));
      expect(state[GrowthMorphs.fatGynoid],
          closeTo(0.7 * preset.fatSplit.gynoid, 1e-9));
      expect(state.fat(preset), closeTo(0.7, 1e-9));
    });

    test('body fat hides abs no matter how hard they are trained', () {
      const trained = {'abs': PartProgress(volume: 1e6)};
      final defined = model.stateFor(const TrainingProgress(parts: trained));
      final buried =
          model.stateFor(const TrainingProgress(parts: trained, fatLevel: 1.0));
      expect(defined['abs'], greaterThan(0.9));
      expect(buried['abs'], lessThan(defined['abs'] * 0.2),
          reason: 'a six-pack on an overweight body reads as wrong');
    });

    test('the male and female presets deposit fat differently', () {
      final manifest = loadManifest();
      final male = manifest.preset('male');
      final female = manifest.preset('female');
      expect(male.fatSplit.android, greaterThan(male.fatSplit.gynoid));
      expect(female.fatSplit.gynoid, greaterThan(female.fatSplit.android));
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
          'pecs': PartProgress(volume: 40, sinceLastSession: Duration(days: 30))
        },
      );
      final after = start.withSession('pecs', 10);
      expect(after.parts['pecs']!.volume, 50);
      expect(after.parts['pecs']!.sinceLastSession, Duration.zero);
    });

    group('stages', () {
      test('spans 0 to stageCount - 1', () {
        expect(model.stageOf('biceps', 0.0), 0);
        expect(model.stageOf('biceps', 1.0), model.stageCount - 1);
        expect(model.stageOf('biceps', 0.5),
            inInclusiveRange(0, model.stageCount - 1));
      });

      test('never decreases as weight rises', () {
        var previous = 0;
        for (var w = 0.0; w <= 1.0; w += 0.01) {
          final stage = model.stageOf('biceps', w);
          expect(stage, greaterThanOrEqualTo(previous));
          previous = stage;
        }
      });

      test('volumeToNextStage is positive below the cap and null at the top',
          () {
        const early = PartProgress(volume: 5);
        expect(model.volumeToNextStage('biceps', early), greaterThan(0));
        const maxed = PartProgress(volume: 1e6);
        expect(model.volumeToNextStage('biceps', maxed), isNull);
      });

      test('adding exactly volumeToNextStage reaches the next stage', () {
        const progress = PartProgress(volume: 30);
        final stage = model.stageOf(
            'biceps', model.curveFor('biceps').weightFor(progress));
        final needed = model.volumeToNextStage('biceps', progress)!;
        final advanced = PartProgress(volume: progress.volume + needed);
        expect(
          model.stageOf('biceps', model.curveFor('biceps').weightFor(advanced)),
          stage + 1,
        );
      });

      test('stageProgress stays within 0..1', () {
        for (final v in [0.0, 1.0, 25.0, 120.0, 400.0, 1e6]) {
          final p = model.stageProgress('biceps', PartProgress(volume: v));
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
        'biceps': PartProgress(volume: 120),
      });
      final state = tuned.stateFor(same);
      expect(state['calves'], lessThan(state['biceps']),
          reason: 'stubborn calves should need more volume for the same look');
    });
  });

  group('BodyState', () {
    test('clamps weights into 0..1', () {
      final state = BodyState({'pecs': 2.5, 'biceps': -1.0});
      expect(state['pecs'], 1.0);
      expect(state['biceps'], 0.0);
    });

    test('unknown morphs read as zero', () {
      expect(BodyState(const {})['nope'], 0.0);
    });

    test('influences follow GLB morph order', () {
      final state = BodyState({'pecs': 0.5});
      final influences = state.influences(preset);
      expect(influences, hasLength(preset.morphTargets.length));
      expect(influences[preset.morph('pecs')!.index], 0.5);
    });

    test('lerp moves from one body to the other', () {
      final a = BodyState.rest(preset);
      final b = BodyState({'pecs': 1.0});
      expect(BodyState.lerp(a, b, 0.0)['pecs'], 0.0);
      expect(BodyState.lerp(a, b, 0.5)['pecs'], closeTo(0.5, 1e-9));
      expect(BodyState.lerp(a, b, 1.0)['pecs'], 1.0);
    });

    test('gainsOver reports what grew, biggest first', () {
      final before = BodyState({'pecs': 0.1, 'biceps': 0.1, 'calves': 0.5});
      final after = BodyState({'pecs': 0.2, 'biceps': 0.5, 'calves': 0.5});
      expect(after.gainsOver(before), ['biceps', 'pecs']);
    });

    test('overall ignores bulk and fat', () {
      final state = BodyState({
        GrowthMorphs.bulk: 1.0,
        GrowthMorphs.fatAndroid: 1.0,
        GrowthMorphs.fatGynoid: 1.0,
      });
      expect(state.overall(preset), 0.0);
    });

    test('archetypes span lean to muscular in the expected order', () {
      final levels = <String, double>{};
      for (final id in ['lean', 'average', 'athletic', 'muscular']) {
        levels[id] = BodyState.archetype(preset, id).overall(preset);
      }
      expect(levels['lean'], lessThan(levels['average']!));
      expect(levels['average'], lessThan(levels['athletic']!));
      expect(levels['athletic'], lessThan(levels['muscular']!));
      expect(levels['lean'], 0.0, reason: 'lean is the base mesh itself');
    });

    test('the overweight archetype is fat, not trained', () {
      final over = BodyState.archetype(preset, 'overweight');
      final muscular = BodyState.archetype(preset, 'muscular');
      expect(over.fat(preset), greaterThan(muscular.fat(preset)));
      expect(over.overall(preset), lessThan(muscular.overall(preset)));
      expect(over['abs'], lessThan(0.1),
          reason: 'abs must be hidden at high body fat');
    });

    test('unknown archetype names fail loudly', () {
      expect(
          () => BodyState.archetype(preset, 'shredded'), throwsArgumentError);
    });
  });
}
