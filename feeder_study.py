# This study estimates solar hosting capacity from a voltage limit.
# It uses pandapower's built-in 33-bus distribution feeder.
from pathlib import Path

import matplotlib
import pandapower as pp
import pandapower.networks as pn

# Use a file-saving backend so the script works without a plot window.
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Create the output folder so a new clone can run without manual setup.
output_folder = Path("outputs")
output_folder.mkdir(exist_ok=True)


# Load the 33-bus, 12.66 kV radial test feeder.
# Bus 0 is the source bus in this built-in network.
net = pn.case33bw()


# Run the baseline power flow before adding any solar.
# net.res_bus stores the calculated voltage at every bus after this step.
pp.runpp(net, numba=False)


# Read the lowest and highest baseline voltages.
# Per-unit voltage uses 1.00 pu as nominal voltage.
min_voltage = net.res_bus.vm_pu.min()
max_voltage = net.res_bus.vm_pu.max()
lowest_bus = net.res_bus.vm_pu.idxmin()

print("STAGE 1 - BASELINE")
print(f"Minimum voltage: {min_voltage:.4f} pu")
print(f"Maximum voltage: {max_voltage:.4f} pu")
print(f"Lowest-voltage bus: {lowest_bus}")


# Check the line table for the 17 expected trunk connections.
# The trunk is 0-1, 1-2, through 16-17.
trunk_connections_found = 0
for bus in range(17):
    forward_line = (net.line.from_bus == bus) & (net.line.to_bus == bus + 1)
    reverse_line = (net.line.from_bus == bus + 1) & (net.line.to_bus == bus)
    if (forward_line | reverse_line).any():
        trunk_connections_found += 1

print(
    "Trunk check from net.line: "
    f"{trunk_connections_found} of 17 connections from buses 0 to 17 were found."
)


# Save the baseline voltage on buses 0 through 17 for later comparison.
trunk_buses = list(range(18))
trunk_voltages = net.res_bus.loc[trunk_buses, "vm_pu"].copy()


# Plot the baseline voltage profile and the simple voltage reference lines.
plt.figure(figsize=(9, 5))
plt.plot(trunk_buses, trunk_voltages, marker="o", label="Baseline voltage")
plt.axhline(0.95, color="red", linestyle="--", label="0.95 pu limit")
plt.axhline(1.05, color="red", linestyle="--", label="1.05 pu limit")
plt.xlabel("Bus number on main trunk")
plt.ylabel("Voltage (pu)")
plt.title("Stage 1: Baseline Voltage Along the Main Trunk")
plt.xticks(trunk_buses)
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(output_folder / "stage1_baseline.png", dpi=150)
plt.close()


# Add one unity-power-factor solar generator at the far end of the trunk.
# q_mvar is zero, so the generator does not supply reactive power.
solar_index = pp.create_sgen(
    net,
    bus=17,
    p_mw=0.0,
    q_mvar=0.0,
    name="Solar at bus 17",
)


# Test the requested solar sizes and keep each voltage profile for plotting.
solar_sizes_mw = [0.5, 2.0, 4.0]
solar_voltage_results = {}

print("\nSTAGE 2 - SOLAR AT BUS 17")
for solar_size in solar_sizes_mw:
    net.sgen.at[solar_index, "p_mw"] = solar_size
    pp.runpp(net, numba=False)
    solar_voltage_results[solar_size] = net.res_bus.loc[
        trunk_buses, "vm_pu"
    ].copy()
    print(
        f"{solar_size:.1f} MW solar: "
        f"minimum = {net.res_bus.vm_pu.min():.4f} pu, "
        f"maximum = {net.res_bus.vm_pu.max():.4f} pu"
    )


# Plot the baseline and all three solar cases on the same graph.
plt.figure(figsize=(9, 5))
plt.plot(trunk_buses, trunk_voltages, marker="o", label="Baseline")
for solar_size in solar_sizes_mw:
    plt.plot(
        trunk_buses,
        solar_voltage_results[solar_size],
        marker="o",
        label=f"{solar_size:g} MW solar",
    )

plt.axhline(0.95, color="red", linestyle="--", label="0.95 pu limit")
plt.axhline(1.05, color="red", linestyle="--", label="1.05 pu limit")
plt.xlabel("Bus number on main trunk")
plt.ylabel("Voltage (pu)")
plt.title("Stage 2: Effect of Solar at Bus 17")
plt.xticks(trunk_buses)
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(output_folder / "stage2_solar_at_end.png", dpi=150)
plt.close()


# Test solar at three locations to find each voltage hosting capacity.
# The last accepted 0.25 MW step is the hosting-capacity result.
study_buses = [5, 10, 17]
hosting_capacities_mw = []
first_violations_mw = []

for study_bus in study_buses:
    net.sgen.at[solar_index, "bus"] = study_bus
    hosting_capacity = 0.0

    # Increase solar in 0.25 MW steps and check the maximum voltage at all buses.
    for step in range(1, 201):
        solar_size = step * 0.25
        net.sgen.at[solar_index, "p_mw"] = solar_size
        pp.runpp(net, numba=False)

        if net.res_bus.vm_pu.max() > 1.05:
            first_violation = solar_size
            break

        hosting_capacity = solar_size

    hosting_capacities_mw.append(hosting_capacity)
    first_violations_mw.append(first_violation)


# Print the hosting-capacity table.
print("\nSTAGE 3 - VOLTAGE HOSTING CAPACITY")
print("Bus   Hosting capacity   First size above 1.05 pu")
for result_number in range(len(study_buses)):
    print(
        f"{study_buses[result_number]:>3}   "
        f"{hosting_capacities_mw[result_number]:>7.2f} MW          "
        f"{first_violations_mw[result_number]:>7.2f} MW"
    )


# Plot the three hosting-capacity values as a bar chart.
bus_labels = [f"Bus {bus}" for bus in study_buses]
plt.figure(figsize=(8, 5))
plt.bar(bus_labels, hosting_capacities_mw, color="goldenrod")
plt.ylabel("Solar hosting capacity (MW)")
plt.title("Stage 3: Hosting Capacity Before Voltage Exceeds 1.05 pu")
plt.grid(axis="y", alpha=0.3)

for result_number in range(len(study_buses)):
    plt.text(
        result_number,
        hosting_capacities_mw[result_number] + 0.1,
        f"{hosting_capacities_mw[result_number]:.2f} MW",
        ha="center",
    )

plt.tight_layout()
plt.savefig(output_folder / "stage3_hosting_capacity.png", dpi=150)
plt.close()
