"""Turns a Character into a GLB file."""

from . import glb
from .rig import EXT_HUMANOID, HUMANOID_BONES


def export_glb(character, path, face_png, humanoid_extension=True):
    b = glb.GLBBuilder()
    rig = character.rig

    # -- joints ------------------------------------------------------------
    # joints occupy node indices 0..N-1 so skin.joints can reference them
    # directly, before any mesh nodes are appended
    for bone in rig.bones:
        b.add_node(name=bone.name, translation=rig.local_translation(bone.name))
    for bone in rig.bones:
        if bone.children:
            b.set_children(bone.index, [rig.by_name[c].index for c in bone.children])

    ibm = b.add_accessor(
        [rig.inverse_bind(bone.name) for bone in rig.bones],
        "MAT4", name="inverseBindMatrices",
    )
    skin = b.add_skin("Armature", [bone.index for bone in rig.bones], ibm,
                      skeleton=rig.by_name["Root"].index)

    # -- materials ---------------------------------------------------------
    p = character.p
    face_tex = b.add_texture(face_png, name="FaceTexture")
    materials = {
        "skin": b.add_material("Skin", p.skin_color, roughness=0.78),
        "face": b.add_material("Face", p.face_color, roughness=0.62,
                               base_color_texture=face_tex),
        "accent": b.add_material("Outfit", p.accent_color, roughness=0.55),
    }

    # -- meshes ------------------------------------------------------------
    mesh_names = []
    mesh_nodes = []
    sparse_stats = {"targets": 0, "sparse": 0}
    for group in character.groups:
        mesh = group.mesh
        if mesh.vertex_count == 0:
            continue
        index_type = (glb.UNSIGNED_SHORT if mesh.vertex_count < 65536
                      else glb.UNSIGNED_INT)
        attributes = {
            "POSITION": b.add_accessor(mesh.positions, "VEC3",
                                       target=glb.ARRAY_BUFFER),
            "NORMAL": b.add_accessor(mesh.normals, "VEC3",
                                     target=glb.ARRAY_BUFFER),
            "JOINTS_0": b.add_accessor(group.joints, "VEC4",
                                       component_type=glb.UNSIGNED_BYTE,
                                       target=glb.ARRAY_BUFFER),
            "WEIGHTS_0": b.add_accessor(group.weights, "VEC4",
                                        target=glb.ARRAY_BUFFER),
        }
        if group.textured:
            attributes["TEXCOORD_0"] = b.add_accessor(
                mesh.uvs, "VEC2", target=glb.ARRAY_BUFFER)
        primitive = {
            "attributes": attributes,
            "indices": b.add_accessor(mesh.indices, "SCALAR",
                                      component_type=index_type,
                                      target=glb.ELEMENT_ARRAY_BUFFER),
            "material": materials[group.material],
        }
        target_names = None
        if group.targets:
            # sparse: a mask for one muscle touches a small share of the mesh,
            # so storing dense deltas per target would dominate the file
            primitive["targets"] = [
                {
                    "POSITION": b.add_sparse_accessor(
                        t["positions"], "VEC3", name=f'{t["name"]}.position'),
                    "NORMAL": b.add_sparse_accessor(
                        t["normals"], "VEC3", name=f'{t["name"]}.normal'),
                }
                for t in group.targets
            ]
            target_names = [t["name"] for t in group.targets]
            for t in group.targets:
                sparse_stats["targets"] += 1
                if t["touched"] < mesh.vertex_count * 0.6:
                    sparse_stats["sparse"] += 1

        mesh_index = b.add_mesh(
            mesh.name, [primitive],
            weights=[0.0] * len(group.targets) if group.targets else None,
            target_names=target_names,
        )
        mesh_names.append(mesh.name)
        mesh_nodes.append(b.add_node(name=mesh.name, mesh=mesh_index, skin=skin))

    b.add_root(rig.by_name["Root"].index)
    for node in mesh_nodes:
        b.add_root(node)

    # -- humanoid bone mapping --------------------------------------------
    if humanoid_extension:
        # Additive metadata only, and NOT declared as required: a runtime that
        # ignores it still loads a correct character. What it buys is humanoid
        # animation remapping by bone role instead of by node index.
        b.declare_extension(EXT_HUMANOID, required=False)
        b.set_root_extension(EXT_HUMANOID, {
            "humanoidSkeletons": [{
                "rootNode": rig.by_name["Root"].index,
                "humanoidBones": {
                    humanoid: rig.by_name[node].index
                    for node, humanoid in HUMANOID_BONES.items()
                    if node in rig.by_name
                },
            }],
        })

    size = b.save_glb(path)
    return {
        "bytes": size,
        "meshes": mesh_names,
        "morphTargets": [g.name for g in character.morph_groups],
        "sparseTargets": sparse_stats,
    }
