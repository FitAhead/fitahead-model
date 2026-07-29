import 'manifest.dart';

/// The morph target weights that describe how the character currently looks.
///
/// Immutable: a workout produces a new state, and the UI animates from the old
/// one to the new one so the change is something the user watches happen.
class BodyState {
  BodyState(Map<String, double> weights)
      : weights = Map.unmodifiable({
          for (final e in weights.entries) e.key: e.value.clamp(0.0, 1.0),
        });

  /// Everything at rest: the untrained starting body.
  factory BodyState.rest(CharacterPreset preset) =>
      BodyState({for (final m in preset.morphTargets) m.name: 0.0});

  final Map<String, double> weights;

  double operator [](String morph) => weights[morph] ?? 0.0;

  /// Weights in GLB morph order, for renderers that take a positional list.
  List<double> influences(CharacterPreset preset) =>
      [for (final m in preset.morphTargets) this[m.name]];

  BodyState copyWith(Map<String, double> overrides) =>
      BodyState({...weights, ...overrides});

  /// Mean weight across the trainable groups, ignoring `bulk` (which is derived
  /// from the others) and any regression shape like `belly`.
  double overall(CharacterPreset preset) {
    var sum = 0.0;
    var count = 0;
    for (final m in preset.morphTargets) {
      if (m.isRegression || m.name == GrowthMorphs.bulk) continue;
      sum += this[m.name];
      count++;
    }
    return count == 0 ? 0.0 : sum / count;
  }

  static BodyState lerp(BodyState a, BodyState b, double t) {
    final keys = {...a.weights.keys, ...b.weights.keys};
    return BodyState({
      for (final k in keys) k: a[k] + (b[k] - a[k]) * t,
    });
  }

  /// Morphs whose weight rose by more than [threshold] — what to celebrate
  /// after a session, and which body part to fly the camera to.
  List<String> gainsOver(BodyState previous, {double threshold = 0.01}) {
    final gains = <String, double>{};
    for (final entry in weights.entries) {
      final delta = entry.value - previous[entry.key];
      if (delta > threshold) gains[entry.key] = delta;
    }
    final sorted = gains.keys.toList()
      ..sort((a, b) => gains[b]!.compareTo(gains[a]!));
    return sorted;
  }

  @override
  String toString() {
    final parts = weights.entries
        .where((e) => e.value > 0.001)
        .map((e) => '${e.key}=${e.value.toStringAsFixed(2)}')
        .join(', ');
    return 'BodyState($parts)';
  }
}

/// Morph target names that carry special meaning to the growth model.
abstract final class GrowthMorphs {
  /// Overall size — derived from the other groups rather than trained directly.
  static const bulk = 'bulk';

  /// Belly — driven by body composition, not by training volume.
  static const belly = 'belly';
}
