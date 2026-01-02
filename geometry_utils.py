import numpy

def calculate_obb_pca(vertices):
    """
    Calculate the Oriented Bounding Box (OBB) of a set of points using PCA.

    Args:
        vertices (np.ndarray): A Nx3 array of points.

    Returns:
        dict: A dictionary containing:
            'center' (np.ndarray): The center of the OBB.
            'extents' (np.ndarray): The half-lengths of the OBB along its axes.
            'rotation' (np.ndarray): A 3x3 rotation matrix representing the OBB's orientation.
    """
    if len(vertices) == 0:
        return {
            'center': numpy.zeros(3),
            'extents': numpy.zeros(3),
            'rotation': numpy.identity(3)
        }

    mean = numpy.mean(vertices, axis=0)
    centered_vertices = vertices - mean
    covariance_matrix = numpy.cov(centered_vertices, rowvar=False)
    eigenvalues, eigenvectors = numpy.linalg.eigh(covariance_matrix)
    rotation_matrix = eigenvectors
    projected_vertices = centered_vertices @ rotation_matrix
    min_projections = numpy.min(projected_vertices, axis=0)
    max_projections = numpy.max(projected_vertices, axis=0)
    obb_center_in_obb_space = (min_projections + max_projections) / 2.0
    obb_center = mean + obb_center_in_obb_space @ rotation_matrix.T
    obb_extents = (max_projections - min_projections) / 2.0

    return {
        'center': obb_center,
        'extents': obb_extents,
        'rotation': rotation_matrix
    }

def sat_check_obb_triangle(obb, triangle_vertices):
    """
    Check for intersection between an OBB and a triangle using the Separating Axis Theorem (SAT).

    Args:
        obb (dict): OBB dictionary with 'center', 'extents', and 'rotation'.
        triangle_vertices (np.ndarray): A 3x3 array of triangle vertex positions.

    Returns:
        bool: True if they intersect, False otherwise.
    """
    obb_center = obb['center']
    obb_extents = obb['extents']
    obb_axes = [obb['rotation'][:, i] for i in range(3)]
    tri_v0, tri_v1, tri_v2 = triangle_vertices
    tri_edges = [tri_v1 - tri_v0, tri_v2 - tri_v1, tri_v0 - tri_v2]

    axes_to_test = []
    axes_to_test.extend(obb_axes)

    tri_normal = numpy.cross(tri_edges[0], tri_edges[1])
    tri_normal_norm = numpy.linalg.norm(tri_normal)
    if tri_normal_norm > 1e-6:
        axes_to_test.append(tri_normal / tri_normal_norm)

    for i in range(3):
        for j in range(3):
            cross_product = numpy.cross(obb_axes[i], tri_edges[j])
            cross_product_norm = numpy.linalg.norm(cross_product)
            if cross_product_norm > 1e-6:
                axes_to_test.append(cross_product / cross_product_norm)

    for axis in axes_to_test:
        obb_dot_axes = numpy.abs([numpy.dot(axis, obb_ax) for obb_ax in obb_axes])
        r = numpy.dot(obb_extents, obb_dot_axes)

        obb_projection = numpy.dot(obb_center, axis)
        obb_interval = (obb_projection - r, obb_projection + r)

        tri_projections = numpy.dot(triangle_vertices, axis)
        tri_interval = (numpy.min(tri_projections), numpy.max(tri_projections))

        if obb_interval[1] < tri_interval[0] or tri_interval[1] < obb_interval[0]:
            return False

    return True

def check_obb_mesh_collision(obb, mesh_vertices, mesh_indices, excluded_faces=None):
    """
    Check if an OBB collides with any triangle in a mesh.

    Args:
        obb (dict): The OBB to check.
        mesh_vertices (np.ndarray): The vertices of the mesh.
        mesh_indices (np.ndarray): The indices of the mesh.
        excluded_faces (set, optional): A set of face indices to ignore during collision checks.

    Returns:
        bool: True if a collision is found, False otherwise.
    """
    if excluded_faces is None:
        excluded_faces = set()

    for i, face in enumerate(mesh_indices):
        if i in excluded_faces:
            continue
        triangle = mesh_vertices[face]
        if sat_check_obb_triangle(obb, triangle):
            return True
    return False
