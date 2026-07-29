"""Dependency-free glTF 2.0 / GLB writer.

Only the subset FitAhead needs: one skinned mesh with morph targets, a joint
hierarchy, and PBR materials. Everything lives in a single binary buffer, which
is what the GLB container wants anyway.
"""

import json
import struct

# glTF componentType constants
FLOAT = 5126
UNSIGNED_SHORT = 5123
UNSIGNED_BYTE = 5121
UNSIGNED_INT = 5125

# bufferView target constants
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963

_COMPONENT_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_COMPONENT_FMT = {
    FLOAT: "f",
    UNSIGNED_SHORT: "H",
    UNSIGNED_BYTE: "B",
    UNSIGNED_INT: "I",
}
_COMPONENT_SIZE = {FLOAT: 4, UNSIGNED_SHORT: 2, UNSIGNED_BYTE: 1, UNSIGNED_INT: 4}


class GLBBuilder:
    def __init__(self, generator="fitahead-model"):
        self.json = {
            "asset": {"version": "2.0", "generator": generator},
            "scene": 0,
            "scenes": [{"nodes": []}],
            "nodes": [],
            "meshes": [],
            "materials": [],
            "skins": [],
            "accessors": [],
            "bufferViews": [],
            "images": [],
            "samplers": [],
            "textures": [],
        }
        self._blob = bytearray()

    # -- binary buffer -----------------------------------------------------

    def _append_bytes(self, data, target=None):
        # bufferView offsets must be aligned to the component size; 4 covers all
        while len(self._blob) % 4 != 0:
            self._blob.append(0)
        offset = len(self._blob)
        self._blob.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.json["bufferViews"].append(view)
        return len(self.json["bufferViews"]) - 1

    def add_accessor(self, values, accessor_type, component_type=FLOAT,
                     target=None, normalized=False, name=None):
        """`values` is a flat list, or a list of per-element tuples/lists."""
        n = _COMPONENT_COUNT[accessor_type]
        flat = []
        for v in values:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        count = len(flat) // n
        assert len(flat) == count * n, f"{accessor_type} needs a multiple of {n}"

        fmt = "<" + _COMPONENT_FMT[component_type] * len(flat)
        data = struct.pack(fmt, *flat)
        view = self._append_bytes(data, target=target)

        accessor = {
            "bufferView": view,
            "componentType": component_type,
            "count": count,
            "type": accessor_type,
        }
        if normalized:
            accessor["normalized"] = True
        if name:
            accessor["name"] = name
        # min/max are required on POSITION accessors and harmless elsewhere
        if accessor_type in ("VEC3", "VEC2", "SCALAR") and component_type == FLOAT:
            mins = [min(flat[i::n]) for i in range(n)]
            maxs = [max(flat[i::n]) for i in range(n)]
            accessor["min"] = mins
            accessor["max"] = maxs
        self.json["accessors"].append(accessor)
        return len(self.json["accessors"]) - 1

    # -- scene graph -------------------------------------------------------

    def add_node(self, name=None, translation=None, rotation=None, scale=None,
                 children=None, mesh=None, skin=None):
        node = {}
        if name:
            node["name"] = name
        if translation:
            node["translation"] = list(translation)
        if rotation:
            node["rotation"] = list(rotation)
        if scale:
            node["scale"] = list(scale)
        if children:
            node["children"] = list(children)
        if mesh is not None:
            node["mesh"] = mesh
        if skin is not None:
            node["skin"] = skin
        self.json["nodes"].append(node)
        return len(self.json["nodes"]) - 1

    def set_children(self, node_index, children):
        if children:
            self.json["nodes"][node_index]["children"] = list(children)

    def add_root(self, node_index):
        self.json["scenes"][0]["nodes"].append(node_index)

    def add_material(self, name, base_color, roughness=0.72, metallic=0.0,
                     base_color_texture=None):
        pbr = {
            "baseColorFactor": list(base_color),
            "metallicFactor": metallic,
            "roughnessFactor": roughness,
        }
        if base_color_texture is not None:
            pbr["baseColorTexture"] = {"index": base_color_texture}
        self.json["materials"].append({"name": name, "pbrMetallicRoughness": pbr})
        return len(self.json["materials"]) - 1

    def add_texture(self, png_bytes, name="texture"):
        view = self._append_bytes(png_bytes)
        self.json["images"].append(
            {"name": name, "bufferView": view, "mimeType": "image/png"}
        )
        if not self.json["samplers"]:
            # linear filtering, clamp to edge so a face drawing never tiles
            self.json["samplers"].append(
                {"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}
            )
        self.json["textures"].append(
            {"name": name, "source": len(self.json["images"]) - 1, "sampler": 0}
        )
        return len(self.json["textures"]) - 1

    def add_mesh(self, name, primitives, weights=None, target_names=None):
        mesh = {"name": name, "primitives": primitives}
        if weights:
            mesh["weights"] = list(weights)
        if target_names:
            mesh["extras"] = {"targetNames": list(target_names)}
        self.json["meshes"].append(mesh)
        return len(self.json["meshes"]) - 1

    def add_skin(self, name, joints, inverse_bind_accessor, skeleton=None):
        skin = {
            "name": name,
            "joints": list(joints),
            "inverseBindMatrices": inverse_bind_accessor,
        }
        if skeleton is not None:
            skin["skeleton"] = skeleton
        self.json["skins"].append(skin)
        return len(self.json["skins"]) - 1

    # -- output ------------------------------------------------------------

    def _finalize_json(self):
        doc = dict(self.json)
        doc["buffers"] = [{"byteLength": len(self._blob)}]
        # drop empty arrays: the spec forbids zero-length ones
        return {k: v for k, v in doc.items() if not (isinstance(v, list) and not v)}

    def save_glb(self, path):
        doc = self._finalize_json()
        json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
        json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
        bin_bytes = bytes(self._blob)
        bin_bytes += b"\x00" * ((4 - len(bin_bytes) % 4) % 4)

        total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
            f.write(json_bytes)
            f.write(struct.pack("<II", len(bin_bytes), 0x004E4942))
            f.write(bin_bytes)
        return total
