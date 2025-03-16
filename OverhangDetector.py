import trimesh
import numpy as np
from UM.Logger import Logger
from UM.Math.Vector import Vector

class OverhangDetector:
    def __init__(self, picked_node):
        try:
            # Convert the node's MeshData to a Trimesh for geometry queries
            mesh_data = picked_node.getMeshData()
            vertices = mesh_data.getVertices()
            indices = mesh_data.getIndices()
            
            # Validate mesh data
            if vertices is None or len(vertices) == 0:
                Logger.log("e", "No vertices found in mesh data")
                raise ValueError("No vertices in mesh data")
                
            if indices is None or len(indices) == 0:
                Logger.log("e", "No faces found in mesh data")
                raise ValueError("No faces in mesh data")
            
            Logger.log("d", f"Creating Trimesh with {len(vertices)} vertices and {len(indices)} faces")
            
            self.mesh = trimesh.Trimesh(vertices=vertices, 
                                      faces=indices,
                                      process=False)  # process=False to avoid altering geometry
                                      
            # Validate created mesh
            if not self.mesh.is_valid:
                Logger.log("e", "Created mesh is not valid")
                raise ValueError("Invalid mesh created")
                
            # Precompute face adjacency list for BFS/DFS
            adj_pairs = self.mesh.face_adjacency  # (n,2) array of adjacent face index pairs
            self.adjacency = {i: [] for i in range(len(self.mesh.faces))}
            for f1, f2 in adj_pairs:
                self.adjacency[f1].append(f2)
                self.adjacency[f2].append(f1)
                
            # Compute face normals (Trimesh will compute these if not provided)
            self.face_normals = self.mesh.face_normals
            if self.face_normals is None or len(self.face_normals) == 0:
                Logger.log("e", "No face normals computed")
                raise ValueError("No face normals")
                
            # Compute face centers for distance calculations
            self.face_centers = self.mesh.triangles_center
            if self.face_centers is None or len(self.face_centers) == 0:
                Logger.log("e", "No face centers computed")
                raise ValueError("No face centers")
                
            Logger.log("d", f"Successfully initialized OverhangDetector with {len(self.face_centers)} faces")
            
        except Exception as e:
            Logger.log("e", f"Error initializing OverhangDetector: {str(e)}")
            raise  # Re-raise the exception to be handled by caller

    def _find_nearest_face(self, point):
        """Find the face closest to the given point using face centers."""
        try:
            if self.face_centers is None or len(self.face_centers) == 0:
                Logger.log("e", "No face centers available for distance calculation")
                raise ValueError("No face centers available")
                
            point = np.asarray(point)
            # Calculate distances from point to all face centers
            distances = np.linalg.norm(self.face_centers - point, axis=1)
            
            if len(distances) == 0:
                Logger.log("e", "No distances computed")
                raise ValueError("No distances computed")
                
            # Return index of closest face
            nearest_idx = np.argmin(distances)
            Logger.log("d", f"Found nearest face {nearest_idx} at distance {distances[nearest_idx]}")
            return nearest_idx
            
        except Exception as e:
            Logger.log("e", f"Error in _find_nearest_face: {str(e)}")
            raise

    def detectRegion(self, picked_position):
        try:
            # Find the face closest to the picked_position using face centers
            picked_point = np.array([picked_position.x, picked_position.y, picked_position.z])
            Logger.log("d", f"Finding nearest face to point {picked_point}")
            
            face_index = self._find_nearest_face(picked_point)
            Logger.log("d", f"Found starting face {face_index}")

            # 4. Traverse connected faces via BFS from the starting face
            region_faces = set([face_index])
            to_visit = [face_index]
            # (Optional) Determine criteria for "local region" – for example, limit by normal angle or count
            start_normal = self.face_normals[face_index]
            while to_visit:
                current = to_visit.pop(0)  # pop(0) for BFS (queue behavior)
                for nbr in self.adjacency.get(current, []):
                    if nbr in region_faces:
                        continue
                    # Example criteria: include neighbor if its normal is similarly downward-facing
                    nbr_normal = self.face_normals[nbr]
                    # Calculate angle between neighbor normal and vertical (down direction)
                    vertical_down = np.array([0, 0, -1])
                    dot = nbr_normal.dot(vertical_down)
                    if dot <= 0:  # face not facing downward, skip it
                        continue
                    region_faces.add(nbr)
                    to_visit.append(nbr)

            # 5. Compute bounding box of all vertices in the region
            region_vertices = np.unique(self.mesh.faces[list(region_faces)].flatten())
            coords = self.mesh.vertices[region_vertices]
            min_corner = coords.min(axis=0)
            max_corner = coords.max(axis=0)
            size = Vector(max_corner[0] - min_corner[0],      # Convert to Vector for Cura
                         max_corner[1] - min_corner[1],
                         max_corner[2] - min_corner[2])
            center = Vector((min_corner[0] + max_corner[0]) / 2,  # Convert to Vector for Cura
                          (min_corner[1] + max_corner[1]) / 2,
                          (min_corner[2] + max_corner[2]) / 2)

            # 6. Determine suggested support angle from face normals in region
            max_angle = 0.0
            up_vector = np.array([0, 0, 1])            # assuming Z+ is upward
            for fi in region_faces:
                normal = self.face_normals[fi]
                # Only consider faces facing downward (normal dot up is negative)
                if normal.dot(up_vector) < 0:
                    # Angle from vertical (0° = vertical, 90° = horizontal)
                    angle = np.degrees(np.arccos(np.clip(abs(normal.dot(up_vector)), -1.0, 1.0)))
                    max_angle = max(max_angle, angle)
            suggested_angle = round(max_angle, 1)  # round or adjust as needed (e.g., to nearest 5°)

            # 7. Return the results
            return size, center, suggested_angle
            
        except Exception as e:
            Logger.log("e", f"Error in detectRegion: {str(e)}")
            # Return default values in case of error
            return Vector(3.0, 3.0, 3.0), picked_position, 45.0
