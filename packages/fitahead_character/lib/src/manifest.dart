import 'dart:convert';

import 'vec3.dart';

/// Parsed form of `assets/models/character_manifest.json`.
///
/// The manifest is generated next to the GLBs by `tools/gen_character.py`, so
/// joint indices, morph target names and camera framings can never drift out of
/// sync with the meshes the app actually loads.
class CharacterManifest {
  const CharacterManifest({
    required this.version,
    required this.faceTexture,
    required this.presets,
  });

  factory CharacterManifest.fromJson(Map<String, dynamic> json) {
    final presets = <String, CharacterPreset>{};
    (json['presets'] as Map<String, dynamic>).forEach((key, value) {
      presets[key] = CharacterPreset.fromJson(value as Map<String, dynamic>);
    });
    return CharacterManifest(
      version: json['version'] as int,
      faceTexture: json['faceTexture'] as String,
      presets: Map.unmodifiable(presets),
    );
  }

  factory CharacterManifest.parse(String source) =>
      CharacterManifest.fromJson(jsonDecode(source) as Map<String, dynamic>);

  final int version;

  /// Filename of the placeholder face texture, relative to the manifest.
  final String faceTexture;

  final Map<String, CharacterPreset> presets;

  CharacterPreset preset(String id) {
    final p = presets[id];
    if (p == null) {
      throw ArgumentError.value(
        id,
        'id',
        'unknown preset; available: ${presets.keys.join(', ')}',
      );
    }
    return p;
  }
}

/// One buildable character: the male or the female body.
class CharacterPreset {
  const CharacterPreset({
    required this.id,
    required this.sex,
    required this.file,
    required this.height,
    required this.meshes,
    required this.face,
    required this.joints,
    required this.morphTargets,
    required this.focusViews,
    required this.focusFovDeg,
  });

  factory CharacterPreset.fromJson(Map<String, dynamic> json) {
    return CharacterPreset(
      id: json['id'] as String,
      sex: json['sex'] as String,
      file: json['file'] as String,
      height: (json['height'] as num).toDouble(),
      meshes: List<String>.unmodifiable(
        (json['meshes'] as List).cast<String>(),
      ),
      face: FaceSlot.fromJson(json['face'] as Map<String, dynamic>),
      joints: List<JointInfo>.unmodifiable(
        (json['joints'] as List)
            .map((e) => JointInfo.fromJson(e as Map<String, dynamic>)),
      ),
      morphTargets: List<MorphTargetInfo>.unmodifiable(
        (json['morphTargets'] as List)
            .map((e) => MorphTargetInfo.fromJson(e as Map<String, dynamic>)),
      ),
      focusViews: List<FocusView>.unmodifiable(
        (json['focusViews'] as List)
            .map((e) => FocusView.fromJson(e as Map<String, dynamic>)),
      ),
      focusFovDeg: (json['focusFovDeg'] as num).toDouble(),
    );
  }

  final String id;
  final String sex;

  /// GLB filename, relative to the manifest.
  final String file;

  /// Total body height in metres, at rest with every morph at zero.
  final double height;

  final List<String> meshes;
  final FaceSlot face;
  final List<JointInfo> joints;
  final List<MorphTargetInfo> morphTargets;
  final List<FocusView> focusViews;
  final double focusFovDeg;

  /// Morph target names in GLB order — the order `morphTargetInfluences`
  /// expects when a renderer does not expose a name lookup.
  List<String> get morphNames => [for (final m in morphTargets) m.name];

  MorphTargetInfo? morph(String name) {
    for (final m in morphTargets) {
      if (m.name == name) return m;
    }
    return null;
  }

  FocusView? view(String id) {
    for (final v in focusViews) {
      if (v.id == id) return v;
    }
    return null;
  }

  /// Views that map onto a trainable muscle group, in manifest order.
  List<FocusView> get trainableViews => [
        for (final v in focusViews)
          if (v.morph != null) v
      ];
}

/// Where the user's own face drawing goes.
class FaceSlot {
  const FaceSlot({
    required this.mesh,
    required this.material,
    required this.uvLayout,
    required this.defaultTexture,
  });

  factory FaceSlot.fromJson(Map<String, dynamic> json) => FaceSlot(
        mesh: json['mesh'] as String,
        material: json['material'] as String,
        uvLayout: json['uvLayout'] as String,
        defaultTexture: json['defaultTexture'] as String,
      );

  /// Name of the mesh carrying the face plate.
  final String mesh;

  /// Name of the material whose base colour texture to swap.
  final String material;

  /// How the plate's UVs are laid out; `disc-inscribed-in-square` means a
  /// square image is shown as the largest circle that fits inside it.
  final String uvLayout;

  final String defaultTexture;
}

class JointInfo {
  const JointInfo({
    required this.index,
    required this.name,
    required this.parent,
    required this.rest,
  });

  factory JointInfo.fromJson(Map<String, dynamic> json) => JointInfo(
        index: json['index'] as int,
        name: json['name'] as String,
        parent: json['parent'] as String?,
        rest: Vec3.fromList(json['rest'] as List),
      );

  final int index;
  final String name;
  final String? parent;

  /// Rest-pose position in model space, in metres.
  final Vec3 rest;
}

/// A blend shape: one muscle group that can grow.
class MorphTargetInfo {
  const MorphTargetInfo({
    required this.index,
    required this.name,
    required this.labelKo,
    required this.labelEn,
    required this.maxDisplacement,
    required this.isRegression,
  });

  factory MorphTargetInfo.fromJson(Map<String, dynamic> json) =>
      MorphTargetInfo(
        index: json['index'] as int,
        name: json['name'] as String,
        labelKo: json['labelKo'] as String,
        labelEn: json['labelEn'] as String,
        maxDisplacement: (json['maxDisplacement'] as num).toDouble(),
        isRegression: json['isRegression'] as bool,
      );

  final int index;
  final String name;
  final String labelKo;
  final String labelEn;

  /// How far the surface moves, in metres, at weight 1.0.
  final double maxDisplacement;

  /// True for shapes that represent losing condition rather than gaining it —
  /// `belly` is the only one today, and it is driven by body fat, not training.
  final bool isRegression;
}

/// A camera framing for the whole body or for one body part.
///
/// [yawDeg] is measured around +Y with 0 facing the character's front (+Z), and
/// [pitchDeg] is degrees above the horizon.
class FocusView {
  const FocusView({
    required this.id,
    required this.labelKo,
    required this.labelEn,
    required this.target,
    required this.yawDeg,
    required this.pitchDeg,
    required this.distance,
    required this.framingRadius,
    required this.morph,
  });

  factory FocusView.fromJson(Map<String, dynamic> json) => FocusView(
        id: json['id'] as String,
        labelKo: json['labelKo'] as String,
        labelEn: json['labelEn'] as String,
        target: Vec3.fromList(json['target'] as List),
        yawDeg: (json['yawDeg'] as num).toDouble(),
        pitchDeg: (json['pitchDeg'] as num).toDouble(),
        distance: (json['distance'] as num).toDouble(),
        framingRadius: (json['framingRadius'] as num).toDouble(),
        morph: json['morph'] as String?,
      );

  final String id;
  final String labelKo;
  final String labelEn;

  /// Point the camera looks at, in model space.
  final Vec3 target;

  final double yawDeg;
  final double pitchDeg;

  /// Nominal camera distance for the manifest's own field of view and a square
  /// viewport. Prefer deriving it from [framingRadius] at runtime so the shot
  /// survives a different aspect ratio.
  final double distance;

  /// Radius of the sphere this view is meant to fill.
  final double framingRadius;

  /// Morph target this view showcases, or null for whole-body views.
  final String? morph;
}
