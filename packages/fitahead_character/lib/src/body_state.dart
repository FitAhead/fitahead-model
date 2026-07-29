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

  /// The base mesh: untrained, low body fat. Every morph at zero.
  factory BodyState.rest(CharacterPreset preset) =>
      BodyState({for (final m in preset.morphTargets) m.name: 0.0});

  /// One of the manifest's named body types — 마른 / 평범 / 근육질 and friends.
  ///
  /// These are points in morph space rather than separate assets, which is why
  /// the app can also animate between them.
  factory BodyState.archetype(CharacterPreset preset, String id) {
    final archetype = preset.archetype(id);
    if (archetype == null) {
      throw ArgumentError.value(
        id,
        'id',
        'unknown archetype; available: '
            '${preset.archetypes.map((a) => a.id).join(', ')}',
      );
    }
    return BodyState(archetype.weights);
  }

  final Map<String, double> weights;

  double operator [](String morph) => weights[morph] ?? 0.0;

  /// Weights in GLB morph order, for renderers that take a positional list.
  List<double> influences(CharacterPreset preset) =>
      [for (final m in preset.morphTargets) this[m.name]];

  BodyState copyWith(Map<String, double> overrides) =>
      BodyState({...weights, ...overrides});

  /// Mean weight across the trainable muscle groups. Excludes fat and the
  /// derived `bulk` shape, so it reads as "how trained is this body".
  double overall(CharacterPreset preset) {
    final groups = preset.muscleGroups;
    if (groups.isEmpty) return 0.0;
    var sum = 0.0;
    for (final m in groups) {
      sum += this[m.name];
    }
    return sum / groups.length;
  }

  /// Total body fat, recombined from the two deposition patterns.
  double fat(CharacterPreset preset) {
    final split = preset.fatSplit;
    final total = split.android + split.gynoid;
    if (total <= 0) return 0.0;
    // The two weights are `fat * share`, so recovering fat means summing them
    // and dividing by the summed shares — NOT weighting each by its share
    // again, which is the mistake this once made and which under-reported body
    // fat by a third.
    return (this[GrowthMorphs.fatAndroid] + this[GrowthMorphs.fatGynoid]) /
        total;
  }

  static BodyState lerp(BodyState a, BodyState b, double t) {
    final keys = {...a.weights.keys, ...b.weights.keys};
    return BodyState({
      // endpoint-exact so an animation lands on its target rather than near it
      for (final k in keys) k: a[k] * (1 - t) + b[k] * t,
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

/// Morph target names the growth model treats specially.
abstract final class GrowthMorphs {
  /// Overall lean mass — derived from the muscle groups, not trained directly.
  static const bulk = 'bulk';

  /// Abdominal ("apple") fat. Driven by body composition.
  static const fatAndroid = 'fat_android';

  /// Gluteofemoral ("pear") fat. Driven by body composition.
  static const fatGynoid = 'fat_gynoid';

  /// Rectus abdominis. Special-cased because its visibility depends on body fat
  /// as much as on training.
  static const abs = 'abs';
}
