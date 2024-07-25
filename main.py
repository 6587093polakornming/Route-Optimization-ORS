import tkinter as tk
from tkinter import filedialog, messagebox
import openrouteservice as ors
import pandas as pd
import webbrowser
from collections import defaultdict, deque
from itertools import cycle
import folium
from folium.plugins import MarkerCluster
from sklearn.cluster import KMeans
from imblearn.over_sampling import RandomOverSampler
data = None

# Function to generate a list of colors for the routes
def generate_colors(n):
    colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 
              'beige', 'darkblue', 'darkgreen', 'cadetblue', 'pink', 'lightblue', 
              'lightgreen', 'gray', 'black', 'lightgray']
    return colors * (n // len(colors) + 1)

def create_map(vehicles, client):
    colors = generate_colors(len(vehicles))
    map_osm = folium.Map(location=[14.0828151, 100.6258423], zoom_start=12)
    marker_cluster = MarkerCluster().add_to(map_osm)
    delivery_details = ""

    for vehicle_id, orders in vehicles.items():
        if len(orders) == 0:
            continue

        color = colors[vehicle_id]
        jobs = []
        for idx, order in enumerate(orders):
            coord = (order['Lng'], order['Lat'])
            jobs.append(ors.optimization.Job(id=idx, location=list(coord), amount=[1]))
            # order detail
            # print(order)
            order_number = order['Order Number']
            additional_info = f"Region: {order['Region']}, {order['Total weights per order']}"

            delivery_details += f"<div>Vehicle {vehicle_id}, Order {order_number}<br>{additional_info}</div>"

            folium.Marker(
                location=list(reversed(coord)),
                popup=f"Location {list(reversed(coord))} Vehicle {vehicle_id}, Order {order_number}<br>{additional_info}",
                icon=folium.Icon(color=color, icon='info-sign')
            ).add_to(marker_cluster)

        vehicle_list = [ors.optimization.Vehicle(id=vehicle_id, profile='driving-car', start=[100.6258423, 14.0828151], end=[100.6258423, 14.0828151], capacity=[30])]

        try:
            optimized = client.optimization(jobs=jobs, vehicles=vehicle_list, geometry=True)
        except ors.exceptions.ApiError as e:
            print(f"Error optimizing vehicle {vehicle_id}: {e}")
            continue

        for route in optimized['routes']:
            vehicle_id = route['vehicle']
            coordinates = [list(reversed(coords)) for coords in ors.convert.decode_polyline(route['geometry'])['coordinates']]

            folium.PolyLine(locations=coordinates, color=color, tooltip=f"Route for Vehicle {vehicle_id}").add_to(map_osm)

    folium.Marker(
        location=[14.0828151, 100.6258423],
        popup=folium.Popup("Start", max_width=300),
        icon=folium.Icon(color='blue', icon='info-sign')
    ).add_to(map_osm)

    sidebar = f"""
    <div style="position:fixed; top:10px; left:10px; width:300px; height:90%; overflow-y:scroll; background:white; border:2px solid black; padding:10px; z-index:999;">
        <h3>Delivery Details</h3>
        {delivery_details}
    </div>
    """
    map_osm.get_root().html.add_child(folium.Element(sidebar))

    return map_osm

# Function to display delivery details for each vehicle
def display_vehicle_deliveries(vehicles): 
    output = []
    for vehicle_id, orders in vehicles.items():
        output.append(f"Vehicle {vehicle_id} will deliver the following orders:\n")
        for order in orders:
            output.append(f"Order {order['Order Number']} with weight {order['Total weights per order']} kg to location ({order['Lat']}, {order['Lng']})\n")
        output.append("\n")
    return ''.join(output)

# Function to indicate which vehicle is assigned to each order
def display_order_assignments(vehicles): 
    order_assignments = {}
    output = []
    for vehicle_id, orders in vehicles.items():
        for order in orders:
            order_assignments[order['Order Number']] = vehicle_id

    for order, vehicle_id in order_assignments.items():
        output.append(f"Order {order} is assigned to Vehicle {vehicle_id}\n")

    return ''.join(output)


def check_data(data):
        if data is None:
            messagebox.showerror("Error", "No Dataset")

def import_dataset():
    global data
    file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
    if file_path:
        data = pd.read_csv(file_path)
        messagebox.showinfo("Success", "Dataset imported successfully!")

def find_vehicle_counts(data, max_capacity):
    total_weight = data['Total weights per order'].sum()
    print("total weight", total_weight)
    vehicle_count = total_weight // int(max_capacity_entry.get())
    print("vehicle_count", vehicle_count)
    if total_weight % max_capacity != 0 : vehicle_count +=1
    return int(vehicle_count)

def assign_orders_to_vehicles(data, vehicle_count, max_capacity):
    # Extract the coordinates from the dataset
    coordinates = data[['Lat', 'Lng']].values
    
    # Perform K-means clustering
    kmeans = KMeans(n_clusters=vehicle_count, random_state=0).fit(coordinates)
    data['Cluster'] = kmeans.labels_

    vehicles = defaultdict(list)
    
    # Group orders by clusters
    clusters = [data[data['Cluster'] == i] for i in range(vehicle_count)]
    
    # Flatten the clusters into a list of orders and sort by cluster size (descending)
    orders = sorted([(cluster, row) for cluster in clusters for _, row in cluster.iterrows()], key=lambda x: len(x[0]), reverse=True)
    
    # Assign orders to vehicles
    vehicle_id_cycle = cycle(range(vehicle_count))
    current_vehicle_orders = defaultdict(deque)
    current_vehicle_capacity = defaultdict(int)
    
    for cluster, order in orders:
        order_weight = order['Total weights per order']
        vehicle_id = next(vehicle_id_cycle)
        
        while current_vehicle_capacity[vehicle_id] + order_weight > max_capacity or len(current_vehicle_orders[vehicle_id]) >= 30:
            vehicle_id = next(vehicle_id_cycle)
        
        vehicles[vehicle_id].append(order)
        current_vehicle_orders[vehicle_id].append(order)
        current_vehicle_capacity[vehicle_id] += order_weight
    
    # print(vehicles)
    return vehicles

def create_map_ui():
    # try:
        check_data(data)
        # Openrouteservice API setup
        API_KEY = API_KEY_entry.get()
        client = ors.Client(key=API_KEY)

        global vehicles
        check_data(data)
        max_capacity = int(max_capacity_entry.get())
        if vehicle_count_entry.get() == '':
            vehicle_count = find_vehicle_counts(data, max_capacity)
        else:
            vehicle_count = int(vehicle_count_entry.get())
        vehicles = assign_orders_to_vehicles(data, vehicle_count, max_capacity)
        
        if data['Total weights per order'].sum() > vehicle_count * max_capacity:
            messagebox.showerror("Error", "Not enough vehicle capacity for the total weights!")
            return

        vehicles = assign_orders_to_vehicles(data, vehicle_count, max_capacity)
        route_map = create_map(vehicles, client)
        route_map.save('vehicle_routes.html')
        
        webbrowser.open('vehicle_routes.html')
        messagebox.showinfo("Success", "Map created and saved as vehicle_routes.html")
    # except Exception as err:
    #     print(err)

def save_to_csv(output, filename):
    with open(filename, 'w') as file:
        file.write(output)

def display_deliveries_ui():
    # try:
        check_data(data)
        max_capacity = int(max_capacity_entry.get())
        if vehicle_count_entry.get() == '':
            vehicle_count = find_vehicle_counts(data, max_capacity)
        else:
            vehicle_count = int(vehicle_count_entry.get())
        vehicles = assign_orders_to_vehicles(data, vehicle_count, max_capacity)

        deliveries_window = tk.Toplevel()
        deliveries_window.title("Vehicle Deliveries")
        deliveries_window.geometry("600x400")

        text_area = tk.Text(deliveries_window, wrap=tk.WORD, font=("Helvetica", 14, "bold"))
        text_area.pack(expand=True, fill='both')

        output = display_vehicle_deliveries(vehicles)
        text_area.insert(tk.END, output)

        def save_deliveries():
            save_filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if save_filename:
                save_to_csv(output, save_filename)
                messagebox.showinfo("Success", f"Deliveries saved to {save_filename}")

        save_button = tk.Button(deliveries_window, text="Save to CSV", command=save_deliveries, font=("Helvetica", 14, "bold"))
        save_button.pack()
    # except Exception as err:
    #     print(err)

def display_assignments_ui():
    # try:
        check_data(data)
        max_capacity = int(max_capacity_entry.get())
        if vehicle_count_entry.get() == '':
            vehicle_count = find_vehicle_counts(data, max_capacity)
        else:
            vehicle_count = int(vehicle_count_entry.get())
        vehicles = assign_orders_to_vehicles(data, vehicle_count, max_capacity)
        
        assignments_window = tk.Toplevel()
        assignments_window.title("Order Assignments")
        assignments_window.geometry("600x400")

        text_area = tk.Text(assignments_window, wrap=tk.WORD, font=("Helvetica", 14, "bold"))
        text_area.pack(expand=True, fill='both')

        output = display_order_assignments(vehicles)
        text_area.insert(tk.END, output)

        def save_assignments():
            save_filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if save_filename:
                save_to_csv(output, save_filename)
                messagebox.showinfo("Success", f"Assignments saved to {save_filename}")

        save_button = tk.Button(assignments_window, text="Save to CSV", command=save_assignments, font=("Helvetica", 14, "bold"))
        save_button.pack()
    # except Exception as err:
    #     print(err)

# Setup Tkinter
root = tk.Tk()
root.title("Route Optimization")

# ปรับขนาดหน้าต่าง
root.geometry("800x600")

# กำหนด Font
label_font = ("Arial", 14)
button_font = ("Arial", 14, "bold")

# สร้าง Frame สำหรับกลุ่ม Input
input_frame = tk.Frame(root)
input_frame.pack(pady=20)

# Input fields for vehicle count and capacity
tk.Label(input_frame, text="Number of Vehicles:", font=label_font).pack(pady=5)
vehicle_count_entry = tk.Entry(input_frame, font=label_font)
vehicle_count_entry.pack(pady=5)

tk.Label(input_frame, text="Max Capacity:", font=label_font).pack(pady=5)
max_capacity_entry = tk.Entry(input_frame, font=label_font)
max_capacity_entry.pack(pady=5)

# Input field for API Key
tk.Label(input_frame, text="OpenRouteService API KEY:", font=label_font).pack(pady=5)
API_KEY_entry = tk.Entry(input_frame, font=label_font)
API_KEY_entry.pack(pady=5)
API_KEY_entry.insert(0, "")  # ตั้งค่า Default API Key


# สร้าง Frame สำหรับปุ่ม
button_frame = tk.Frame(root)
button_frame.pack(pady=20)

# Buttons
tk.Button(button_frame, text="Import Dataset", command=import_dataset, font=button_font).pack(pady=5, padx=10)
tk.Button(button_frame, text="Create Map", command=create_map_ui, font=button_font).pack(pady=5, padx=10)
tk.Button(button_frame, text="Display Vehicle Deliveries", command=display_deliveries_ui, font=button_font).pack(pady=5, padx=10)
tk.Button(button_frame, text="Display Order Assignments", command=display_assignments_ui, font=button_font).pack(pady=5, padx=10)

# Start the Tkinter event loop
root.mainloop()