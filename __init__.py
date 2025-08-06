bl_info = {
    "name": "Planetary Gear Generator",
    "author": "kame404, with gear algorithm based on work by Leemon Baird",
    "version": (0, 1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > GearGen Tab",
    "description": "Generates a planetary gear set. The core gear profile algorithm is based on the Public Domain work by Leemon Baird.",
    "warning": "",
    "doc_url": "",
    "category": "Add Mesh",
}

import bpy
import bmesh
import math

# --- Gear Profile Generation ---
# The following functions for generating the involute gear profile are a Python
# port of the JavaScript implementation found in the "Planetary Gear Simulator".
# Link: https://www.thecatalystis.com/gears/
#
# The JavaScript code itself is an adaptation of the original "Parametric
# Involute Spur Gear" script, which was released into the Public Domain by its
# author, Leemon Baird, in 2011.
# Original Source: http://www.thingiverse.com/thing:5505

def polar(radius, angle):
    """Converts polar coordinates to cartesian coordinates."""
    return (radius * math.cos(angle), radius * math.sin(angle))

def calculate_involute_angle(base_radius, radius):
    """Calculates the involute angle for a given radius."""
    if radius <= base_radius:
        return 0
    # This is the core formula for the involute curve.
    return math.sqrt((radius / base_radius)**2 - 1) - math.acos(base_radius / radius)

def get_involute_point(base_radius, side, angle_offset, radius):
    """Gets a point on the involute curve."""
    if radius < base_radius:
        radius = base_radius
    involute_angle = calculate_involute_angle(base_radius, radius)
    return polar(radius, side * (involute_angle + angle_offset))

def get_tooth_profile_point(fraction, root_radius, base_radius, outer_radius, angle_offset, side):
    """Calculates a point on the tooth face, from root to tip."""
    start_radius = max(base_radius, root_radius)
    current_radius = (1 - fraction) * start_radius + fraction * outer_radius
    return get_involute_point(base_radius, side, angle_offset, current_radius)

def rotate_point_2d(point, angle):
    """Rotates a 2D point around the origin."""
    x, y = point
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)

def build_gear_verts(num_teeth, scale, is_internal=False, pressure_angle_deg=20.0):
    """Builds the 2D vertices for a single gear profile."""
    module = scale
    # Basic gear parameters
    pitch_radius = (module * num_teeth) / 2
    pressure_angle_rad = math.radians(pressure_angle_deg)
    base_radius = pitch_radius * math.cos(pressure_angle_rad)
    
    # Addendum and Dedendum
    outer_radius = pitch_radius + module
    root_radius = pitch_radius - (module * 1.25)

    # Calculate angles for the tooth profile
    half_tooth_thickness_angle = (module * math.pi / 2) / pitch_radius if pitch_radius > 0 else 0
    involute_angle_offset = -calculate_involute_angle(base_radius, pitch_radius) - half_tooth_thickness_angle / 2

    root_start_angle = involute_angle_offset if root_radius < base_radius else -math.pi / num_teeth
    root_end_angle = -involute_angle_offset if root_radius < base_radius else math.pi / num_teeth

    # Generate one tooth profile
    tooth_points = [polar(root_radius, root_start_angle)]
    num_segments = 5  # Number of segments for the curved tooth face
    for i in range(num_segments + 1):
        fraction = i / num_segments
        tooth_points.append(get_tooth_profile_point(fraction, root_radius, base_radius, outer_radius, involute_angle_offset, 1))
    
    for i in range(num_segments, -1, -1):
        fraction = i / num_segments
        tooth_points.append(get_tooth_profile_point(fraction, root_radius, base_radius, outer_radius, involute_angle_offset, -1))
        
    tooth_points.append(polar(root_radius, root_end_angle))
    
    # Rotate the tooth profile to create the full gear
    all_points = []
    tooth_angle = 2 * math.pi / num_teeth
    for i in range(num_teeth):
        rotation = i * tooth_angle
        for point in tooth_points:
            all_points.append(rotate_point_2d(point, rotation))
            
    if is_internal:
        all_points.reverse()
    
    if all_points:
        all_points.append(all_points[0]) # Close the loop
        
    return all_points

def create_gear_object(name, num_teeth, scale, is_internal=False, thickness=1.0, pressure_angle_deg=20.0, ring_margin=4.0):
    """Creates a gear mesh object from the calculated vertices."""
    bm = bmesh.new()
    verts_2d = build_gear_verts(num_teeth, scale, is_internal, pressure_angle_deg)
    if not verts_2d:
        return None

    try:
        if not is_internal:
            # Create a simple face for an external gear
            face_verts = [bm.verts.new((v[0], v[1], 0)) for v in verts_2d]
            bm.faces.new(face_verts)
        else:
            # Create a ring for an internal gear
            pitch_radius = (scale * num_teeth) / 2.0
            ring_margin_size = scale * ring_margin
            outer_radius = pitch_radius + (scale * 2) + ring_margin_size
            num_outer_verts = max(num_teeth * 2, 64)
            
            outer_verts_2d = [polar(outer_radius, 2 * math.pi * i / num_outer_verts) for i in range(num_outer_verts)]
            outer_verts_2d.append(outer_verts_2d[0])

            outer_bverts = [bm.verts.new((v[0], v[1], 0)) for v in outer_verts_2d]
            inner_bverts = [bm.verts.new((v[0], v[1], 0)) for v in verts_2d]
            bm.faces.new(outer_bverts + inner_bverts)
    except ValueError:
        print(f"Warning: Could not create face for {name}. Check gear parameters.")
        bm.free()
        return None

    # Extrude the face to give it thickness
    if thickness > 0 and bm.faces:
        res = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
        extruded_verts = [v for v in res['geom'] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=extruded_verts, vec=(0, 0, thickness))

    # Create mesh and object
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    return bpy.data.objects.new(name, mesh)

class PlanetaryGearProperties(bpy.types.PropertyGroup):
    sun_teeth: bpy.props.IntProperty(name="Sun Teeth", default=32, min=4, max=200)
    planet_teeth: bpy.props.IntProperty(name="Planet Teeth", default=16, min=4, max=200)
    num_planets: bpy.props.IntProperty(name="Number of Planets", default=6, min=1, max=20)
    pressure_angle: bpy.props.FloatProperty(name="Pressure Angle", default=20.0, min=10.0, max=40.0, unit='ROTATION', description="The angle of the tooth face, affecting its shape")
    scale: bpy.props.FloatProperty(name="Module (Scale)", default=0.05, min=0.001, soft_max=1.0, description="Overall size of the gear set (Module)")
    thickness: bpy.props.FloatProperty(name="Thickness", default=0.2, min=0.01, soft_max=2.0, description="Thickness of the solid gears")
    ring_margin: bpy.props.FloatProperty(name="Ring Gear Margin", default=4.0, min=0.5, soft_max=20.0, description="Outer thickness of the Ring Gear, as a multiple of the Module")
    clearance: bpy.props.FloatProperty(name="Clearance", description="The radial gap between gears for 3D printing tolerance. This moves the planet gears outwards and enlarges the ring gear accordingly", default=0.0002, min=0.0, soft_max=0.1, step=1, precision=4, subtype='DISTANCE')

class OBJECT_OT_GeneratePlanetaryGears(bpy.types.Operator):
    bl_idname = "mesh.generate_planetary_gears"
    bl_label = "Generate Planetary Gears"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.window_manager.planetary_gear_props
        module, clearance = props.scale, props.clearance
        ring_teeth = props.sun_teeth + 2 * props.planet_teeth

        # Create Sun Gear
        sun_gear = create_gear_object("SunGear", props.sun_teeth, module, is_internal=False, thickness=props.thickness, pressure_angle_deg=props.pressure_angle)
        if sun_gear:
            # Rotate to align teeth properly
            sun_gear.rotation_euler.z = math.pi / props.sun_teeth if props.sun_teeth > 0 else 0
            context.collection.objects.link(sun_gear)

        # Create Ring Gear (adjust module for clearance)
        effective_module_for_ring = module + (4 * clearance) / ring_teeth if ring_teeth > 0 else module
        ring_gear = create_gear_object("RingGear", ring_teeth, effective_module_for_ring, is_internal=True, thickness=props.thickness, pressure_angle_deg=props.pressure_angle, ring_margin=props.ring_margin)
        if ring_gear:
            context.collection.objects.link(ring_gear)

        # Create Planet Gears
        planet_gear_template = create_gear_object("PlanetGearTemplate", props.planet_teeth, module, is_internal=False, thickness=props.thickness, pressure_angle_deg=props.pressure_angle)
        if planet_gear_template:
            orbit_radius = ((props.sun_teeth + props.planet_teeth) * module) / 2.0 + clearance
            rotation_ratio = 1 + props.sun_teeth / props.planet_teeth if props.planet_teeth > 0 else 1
            
            for i in range(props.num_planets):
                angle = 2 * math.pi * i / props.num_planets
                planet_gear = bpy.data.objects.new(f"PlanetGear_{i+1}", planet_gear_template.data)
                planet_gear.location = (orbit_radius * math.cos(angle), orbit_radius * math.sin(angle), 0)
                # Rotate planet to mesh with sun gear
                planet_gear.rotation_euler.z = math.pi - angle * rotation_ratio
                context.collection.objects.link(planet_gear)
            
            # Clean up template object
            bpy.data.objects.remove(planet_gear_template)
            
        return {'FINISHED'}

class VIEW3D_PT_PlanetaryGearPanel(bpy.types.Panel):
    bl_label = "Planetary Gear Generator"
    bl_idname = "VIEW3D_PT_planetary_gear"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'GearGen'

    def draw(self, context):
        layout = self.layout
        props = context.window_manager.planetary_gear_props
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Gear Configuration", icon='PREFERENCES')
        col.prop(props, "sun_teeth")
        col.prop(props, "planet_teeth")
        col.prop(props, "num_planets")
        
        # Display calculated ring teeth
        row = col.row()
        row.label(text=f"Ring Teeth: {props.sun_teeth + 2 * props.planet_teeth}")
        row.enabled = False
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Geometry", icon='GEOMETRY_NODES')
        col.prop(props, "pressure_angle")
        col.prop(props, "scale")
        col.prop(props, "clearance")
        col.prop(props, "thickness")
        col.prop(props, "ring_margin")
        
        layout.separator()
        layout.operator(OBJECT_OT_GeneratePlanetaryGears.bl_idname, text="Generate Gears", icon='PLAY')

classes_to_register = (
    PlanetaryGearProperties,
    OBJECT_OT_GeneratePlanetaryGears,
    VIEW3D_PT_PlanetaryGearPanel,
)

def register():
    for cls in classes_to_register:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.planetary_gear_props = bpy.props.PointerProperty(type=PlanetaryGearProperties)

def unregister():
    del bpy.types.WindowManager.planetary_gear_props
    for cls in reversed(classes_to_register):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()