import 'dart:math' as math;

import 'body_state.dart';
import 'manifest.dart';

/// Training done on one muscle group.
class PartProgress {
  const PartProgress(
      {required this.volume, this.sinceLastSession = Duration.zero});

  /// Cumulative training volume. The unit is the app's to choose — effective
  /// sets, tonnage, minutes — as long as it is consistent with
  /// [GrowthCurve.halfVolume].
  final double volume;

  /// How long since this group was last trained, for detraining.
  final Duration sinceLastSession;

  PartProgress plus(double added) =>
      PartProgress(volume: volume + added, sinceLastSession: Duration.zero);
}

/// Everything the growth model needs to decide how the body looks.
class TrainingProgress {
  const TrainingProgress({this.parts = const {}, this.bellyLevel = 0.0});

  /// Keyed by morph target name (`chest`, `arms`, …).
  final Map<String, PartProgress> parts;

  /// 0..1 belly fullness, from body composition rather than training. The app
  /// decides how to derive it — measured body fat, weight trend, or a manual
  /// starting choice during onboarding.
  final double bellyLevel;

  TrainingProgress withSession(String morph, double volume) => TrainingProgress(
        parts: {
          ...parts,
          morph: (parts[morph] ?? const PartProgress(volume: 0)).plus(volume),
        },
        bellyLevel: bellyLevel,
      );
}

/// Maps cumulative volume onto a 0..1 morph weight.
///
/// Saturating rather than linear, for two reasons: it matches how hypertrophy
/// actually behaves, and it front-loads visible change so a beginner sees the
/// character move after their first few sessions rather than after a month.
class GrowthCurve {
  const GrowthCurve({
    this.halfVolume = 120.0,
    this.maxWeight = 1.0,
    this.detrainingHalfLife = const Duration(days: 24),
    this.retainedFloor = 0.55,
  })  : assert(halfVolume > 0),
        assert(maxWeight > 0 && maxWeight <= 1.0),
        assert(retainedFloor >= 0 && retainedFloor <= 1);

  /// Volume at which the group reaches half of [maxWeight].
  final double halfVolume;

  /// Ceiling for this group; below 1.0 for groups that should stay subtle.
  final double maxWeight;

  /// Time for the decaying share of volume to halve while untrained.
  final Duration detrainingHalfLife;

  /// Share of accumulated volume that never decays — muscle memory. Without it
  /// a two-week holiday would visibly undo months of work, which is both
  /// physiologically wrong and the opposite of motivating.
  final double retainedFloor;

  double weightFor(PartProgress progress) =>
      _weightForVolume(effectiveVolume(progress));

  double effectiveVolume(PartProgress progress) {
    if (progress.sinceLastSession <= Duration.zero) return progress.volume;
    final idleDays = progress.sinceLastSession.inMinutes / (60 * 24);
    final halfLifeDays = detrainingHalfLife.inMinutes / (60 * 24);
    final decayed = math.pow(0.5, idleDays / halfLifeDays).toDouble();
    return progress.volume * (retainedFloor + (1 - retainedFloor) * decayed);
  }

  double _weightForVolume(double volume) {
    if (volume <= 0) return 0.0;
    return maxWeight * (1 - math.exp(-math.ln2 * volume / halfVolume));
  }

  /// Inverse of [_weightForVolume] — the volume needed to reach [weight].
  ///
  /// Returns infinity at or above [maxWeight], which the curve only approaches.
  double volumeForWeight(double weight) {
    if (weight <= 0) return 0.0;
    if (weight >= maxWeight) return double.infinity;
    return -halfVolume * math.log(1 - weight / maxWeight) / math.ln2;
  }
}

/// Turns training history into a [BodyState].
class GrowthModel {
  GrowthModel({
    required this.preset,
    Map<String, GrowthCurve> curves = const {},
    this.defaultCurve = const GrowthCurve(),
    this.bulkShare = 0.85,
    this.stageCount = 5,
  })  : assert(bulkShare >= 0 && bulkShare <= 1),
        assert(stageCount >= 2),
        curves = Map.unmodifiable(curves);

  final CharacterPreset preset;

  /// Per-group overrides, keyed by morph name.
  final Map<String, GrowthCurve> curves;

  final GrowthCurve defaultCurve;

  /// How strongly the derived `bulk` morph follows the mean of the trained
  /// groups. Under 1.0 so overall size lags the individual parts — training one
  /// group should read as that group growing, not the whole body inflating.
  final double bulkShare;

  /// Number of visible progress steps per group, for badges and progress bars.
  final int stageCount;

  GrowthCurve curveFor(String morph) => curves[morph] ?? defaultCurve;

  BodyState stateFor(TrainingProgress progress) {
    final weights = <String, double>{};
    for (final morph in preset.morphTargets) {
      if (morph.name == GrowthMorphs.bulk) continue;
      if (morph.name == GrowthMorphs.belly) {
        weights[morph.name] = progress.bellyLevel.clamp(0.0, 1.0);
        continue;
      }
      final part = progress.parts[morph.name];
      weights[morph.name] =
          part == null ? 0.0 : curveFor(morph.name).weightFor(part);
    }

    if (preset.morph(GrowthMorphs.bulk) != null) {
      final trained = [
        for (final m in preset.morphTargets)
          if (!m.isRegression && m.name != GrowthMorphs.bulk)
            weights[m.name] ?? 0.0,
      ];
      final mean = trained.isEmpty
          ? 0.0
          : trained.reduce((a, b) => a + b) / trained.length;
      weights[GrowthMorphs.bulk] = mean * bulkShare;
    }
    return BodyState(weights);
  }

  /// 0-based stage of a group, in `[0, stageCount - 1]`.
  int stageOf(String morph, double weight) {
    final max = curveFor(morph).maxWeight;
    final normalized = (weight / max).clamp(0.0, 1.0);
    final scaled = normalized * stageCount;
    // snap to an exact boundary before flooring: volumeToNextStage aims at one,
    // and landing a few ulps short would report the stage the user just left
    final rounded = scaled.roundToDouble();
    final onBoundary = (scaled - rounded).abs() < 1e-9;
    return math.min((onBoundary ? rounded : scaled).floor(), stageCount - 1);
  }

  /// Additional volume needed to reach the next stage of [morph], or null when
  /// the group is already at the top stage.
  double? volumeToNextStage(String morph, PartProgress progress) {
    final curve = curveFor(morph);
    final stage = stageOf(morph, curve.weightFor(progress));
    if (stage >= stageCount - 1) return null;
    final targetWeight = curve.maxWeight * (stage + 1) / stageCount;
    final needed =
        curve.volumeForWeight(targetWeight) - curve.effectiveVolume(progress);
    return math.max(0.0, needed);
  }

  /// Progress through the current stage, 0..1 — the fill of a progress ring.
  double stageProgress(String morph, PartProgress progress) {
    final curve = curveFor(morph);
    final normalized =
        (curve.weightFor(progress) / curve.maxWeight).clamp(0.0, 1.0);
    final scaled = normalized * stageCount;
    return scaled - scaled.floor() == 0 && scaled > 0 ? 1.0 : scaled % 1.0;
  }
}
