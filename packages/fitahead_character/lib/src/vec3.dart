import 'dart:math' as math;

/// A minimal immutable 3D vector.
///
/// Deliberately local rather than pulled from `vector_math`: this package is the
/// engine-agnostic layer, and every renderer has its own vector type to convert
/// into anyway.
class Vec3 {
  const Vec3(this.x, this.y, this.z);

  const Vec3.zero()
      : x = 0,
        y = 0,
        z = 0;

  factory Vec3.fromList(List<dynamic> v) => Vec3(
        (v[0] as num).toDouble(),
        (v[1] as num).toDouble(),
        (v[2] as num).toDouble(),
      );

  final double x;
  final double y;
  final double z;

  Vec3 operator +(Vec3 o) => Vec3(x + o.x, y + o.y, z + o.z);
  Vec3 operator -(Vec3 o) => Vec3(x - o.x, y - o.y, z - o.z);
  Vec3 operator *(double s) => Vec3(x * s, y * s, z * s);

  double get length => math.sqrt(x * x + y * y + z * z);

  Vec3 normalized() {
    final l = length;
    return l < 1e-9 ? const Vec3(0, 1, 0) : Vec3(x / l, y / l, z / l);
  }

  /// Endpoint-exact interpolation: `lerp(a, b, 1)` returns exactly `b`, which
  /// the `a + (b - a) * t` form does not, so an animation lands on its target
  /// instead of a value that is merely very close to it.
  static Vec3 lerp(Vec3 a, Vec3 b, double t) => Vec3(
        a.x * (1 - t) + b.x * t,
        a.y * (1 - t) + b.y * t,
        a.z * (1 - t) + b.z * t,
      );

  List<double> toList() => [x, y, z];

  @override
  String toString() => 'Vec3(${x.toStringAsFixed(4)}, ${y.toStringAsFixed(4)}, '
      '${z.toStringAsFixed(4)})';

  @override
  bool operator ==(Object other) =>
      other is Vec3 && other.x == x && other.y == y && other.z == z;

  @override
  int get hashCode => Object.hash(x, y, z);
}
