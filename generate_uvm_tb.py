import sys # Used for to allow command line arguments
import re # Importing regular expression library. Core for design_scan function.
# The following libraries are very important for report generation adnd command line interaction
import subprocess
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

def design_scan(filename):
    """
    The funtion that will parse sv module and return module name, ports with their respectuve directions, and the interface name.
    parameter: the sv design file (first command line argument)
    """

    # File descriptor to read the contents of the sv design file
    with open(filename, 'r') as file: 
        sv_file = file.read()

    # Using the seach method of RegEx library to scan for module name and mark it as group for later use.
    module_name = re.search(r'\bmodule\s+(\w+)', sv_file).group(1) 

    # Using the RegEx findall method for signals with their direction and width.
    module_ports = re.findall(r'\b(input|output|inout)\s+(?:reg\s+|logic\s+|wire\s+)?(\[[^]]*\])?\s*(\w+);', sv_file)
    
    # Appending a list for with module's port descrition in a tuple format to return
    port_lst = []
    for direction, width, name in module_ports:
        port_lst.append((direction, width, name))

    # Using RegEx to parse Interface name
    interface_name_match = re.search(r'\binterface\s+(\w+)', sv_file)
    interface_name = interface_name_match.group(1) if interface_name_match else None

    return module_name, port_lst, interface_name

def uvm_framework_files_gen(module_name, port_lst, design_type, interface_name):
    """
    The core function for the UVM testbench enivroment generation.
    parameters: 
    module_name: The name fo the design module. Parsed from the prev function
    port_lst: A list of tuples of port definitions. Parsed from the previous function.
    design_type: The 3rd arg. Useful for some sub functions for creation of some components. Parsed from the previous function.
    interface_name: The interface name parsedf from the prev function. Useful for components which employes config_db.
    """

    # A dict with all the functions for generation of sifferent components. The keys are the strings useful for naming the generated files. 
    # The values are the actual functions
    components = {
        'sequence_item': sequence_item_gen(module_name, port_lst),
        'sequence': sequence_gen(module_name),
        'sequencer': sequencer_gen(module_name),
        'driver': driver_gen(module_name, interface_name, port_lst),
        'monitor': monitor_gen(module_name, interface_name, port_lst),
        'scoreboard': scoreboard_gen(module_name, port_lst, design_type),
        'subscribe': subscriber_gen(module_name, port_lst),
        'agent': agent_gen(module_name),
        'env': env_gen(module_name),
        'test': test_gen(module_name),
        'pkg': pkg_gen(module_name),
        'tb': tb_gen(module_name, interface_name, port_lst),
        }

    # Generates the files and prints on the terminal about their generation
    for comp_name, sv_file in components.items():
        filename = f"{module_name}_{comp_name}.sv"
        with open(filename, 'w') as file:
            file.write(sv_file)
        print(filename, "has been created.")

def sequence_item_gen(module_name, port_lst):
    """
    Function to generate the sequence_item responsibe for containing the transactions.
    parameters:
    module_name: The name of the design module.
    port_lst: The list of tuples of port description.
    """

    # Logic for making a string of port declarations
    port_declarations = ""
    for direction, width, port in port_lst:
        if (direction == "input"):
            port_declarations += f"rand bit {width} {port};\n    "
        else:
            port_declarations += f"bit {width} {port};\n    "
    

    # Logic for facory registration
    uvm_factory_registration = ""
    for direction, width, port in port_lst:
        uvm_factory_registration += f"    `uvm_field_int({port}, UVM_ALL_ON)\n    "

    # The following content will be returned which maintains the syntax of an UVM testbench.
    return f"""
class {module_name}_seq_item extends uvm_sequence_item;

    // Port declaration and randomizing them
    {port_declarations}

    // Add your contraints here as per the needs

    function new(input string name = "{module_name}_seq_item");
        super.new(name);
    endfunction: new

    `uvm_object_utils_begin({module_name}_seq_item)
    {uvm_factory_registration}`uvm_object_utils_end

endclass: {module_name}_seq_item
"""

def sequence_gen(module_name):
    """
    Function to generate the sequence for test case generation.
    parameters:
    module_name: The name of the design module.
    """
    
    return f"""
class {module_name}_seq extends uvm_sequence #({module_name}_seq_item);
    `uvm_object_utils({module_name}_seq)

    function new(input string name = "{module_name}_seq");
        super.new(name);
    endfunction: new

    virtual task body();
    // A basic test case for the functionality check
    req = {module_name}_seq_item::type_id::create("req");
    repeat(10) begin
        start_item(req);
        req.randomize();
        finish_item(req);
        // Additional test cases here
    end
    endtask: body

endclass: {module_name}_seq

// Also, if desired, add addional sequences here for more test cases.
"""

def sequencer_gen(module_name):
    """
    Function to generate the sequencer.
    parameters:
    module_name: The name of the design module.
    """
    return f"""
class {module_name}_sequencer extends uvm_sequencer #({module_name}_seq_item);
    `uvm_component_utils({module_name}_sequencer)

    function new(input string name = "{module_name}_sequencer", uvm_component parent = null);
        super.new(name, parent);
    endfunction: new

endclass: {module_name}_sequencer
"""

def driver_gen(module_name, interface_name, port_lst):
    """
    Function to generate the sequence for test case generation.
    parameters:
    module_name: The name of the design module.
    interface_name: interface name of the design. Used for config_db.
    port_lst: list of tuples of ports definitions.
    """
    
    # A logic that filters the input ports from the transaction or sequence_item to drive virtual interface.
    interface_drive = ""
    for direction, width, port in port_lst:
        if direction == "input":
            interface_drive += f"vif.{port} <= req.{port};\n            "

    return f"""
class {module_name}_driver extends uvm_driver#({module_name}_seq_item);
    `uvm_component_utils({module_name}_driver)

    virtual {interface_name} vif;

    function new(input string name = "{module_name}_driver", uvm_component parent = null);
        super.new(name, parent);
    endfunction: new

    virtual function void build_phase(uvm_phase phase);
        req = {module_name}_seq_item::type_id::create("req");
        super.build_phase(phase);
        if (!uvm_config_db#(virtual {interface_name})::get(this, "", "vif", vif))
            `uvm_fatal(get_type_name(), "Virtual interface not dfound in config_db");
    endfunction: build_phase

    virtual task run_phase(uvm_phase phase);
        forever begin
            seq_item_port.get_next_item(req);
            // Driving logic
            {interface_drive}
            `uvm_info(get_type_name(), "Sent transaction to DUT-------------------------", UVM_NONE);
            req.print();
            seq_item_port.item_done();
        end
    endtask: run_phase
endclass: {module_name}_driver
"""

def monitor_gen(module_name, interface_name, port_lst):
    """
    Function to generate the monitor class for receiving response from the DUT.
    parameters:
    module_name: The name of the design module.
    interface_name: interface name of the design. Used for config_db.
    port_lst: list of tuples of ports definitions.
    """
    
    # A logic that filters the input ports to collect response from the interface.
    monitor_logic = ""
    for direction, width, port in port_lst:
        monitor_logic += f"tr.{port} = vif.{port};\n            "

    return f"""
class {module_name}_monitor extends uvm_monitor;
    `uvm_component_utils({module_name}_monitor)

    {module_name}_seq_item tr;
    virtual {interface_name} vif;

    uvm_analysis_port #({module_name}_seq_item) aport;

    function new(input string name = "{module_name}_monitor", uvm_component parent = null);
        super.new(name, parent);
        aport = new("aport", this);
    endfunction: new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        
        tr = {module_name}_seq_item::type_id::create("tr");

        if (!uvm_config_db#(virtual {interface_name})::get(this, "", "vif", vif))
            `uvm_fatal(get_type_name(), "Cannot find vif in the config_db");
    endfunction: build_phase

    virtual task run_phase(uvm_phase phase);
        {module_name}_seq_item tr;
        forever begin
            #10;
            // Collecting response from DUT
            {monitor_logic}

            `uvm_info(get_type_name(), "Send trans to Scoreboard", UVM_NONE);
            tr.print();

            aport.write(tr);
        end
    endtask: run_phase
endclass
"""

def scoreboard_gen(module_name, port_lst, design_type):
    """
    Function to generate the scoreboard to check the test.
    parameters:
    module_name: The name of the design module.
    port_lst: list of tuples of ports definitions.
    design_type: The 3rd command line argument. 
    """
    
    verification_logic = ""
    golden_reference_model = ""

    # The following logic creates the comparision logic and the golden reference model as per the design type.
    if design_type.lower() == "adder":
        for direction, size, port in port_lst:
            if (direction == "output"):
                golden_reference_model = f"expected_output = tr.a + tr.b;\n\t\t"
                verification_logic += f"if (tr.{port} != expected_output)\n\t" 
                verification_logic += f"\t\t`uvm_info(get_type_name(), \"TEST FAILED\", UVM_NONE)\t\n"
                verification_logic += f"\t\telse\n\t\t\t`uvm_info(get_type_name(), \"TEST PASSED\", UVM_NONE)\n\t\t"
    elif design_type.lower() == "alu":
        golden_reference_model = f"""
            case (tr.opcode)
                4'b0000: expected_output = tr.op1 + tr.op2; // ADD
                4'b0001: expected_output = tr.op1 - tr.op2; // SUB
                4'b0010: expected_output = tr.op1 & tr.op2; // AND
                4'b0011: expected_output = tr.op1 | tr.op2; // OR
                default: expected_output = 0;
            endcase
            """
        for direction, size, port in port_lst:
            if direction == "output":
                verification_logic += f"if (tr.{port} != expected_output)\t\n\t\t\t`uvm_info(get_type_name(), \"TEST FAILED\")\n\t\t"
                verification_logic += f"else\t\n\t\t\t`uvm_info(get_type_name(), \"TEST PASSED\")\n\t\t"
    else:  # Generic template
        verification_logic = """
        // Add your reference verificationn logic here
        """

    return f"""
class {module_name}_scoreboard extends uvm_scoreboard;
    `uvm_component_utils({module_name}_scoreboard)

    {module_name}_seq_item tr;

    uvm_analysis_imp#({module_name}_seq_item, {module_name}_scoreboard) aimport;

    function new(string name, uvm_component parent);
        super.new(name, parent);
        aimport = new("aimport", this);
    endfunction: new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        tr = {module_name}_seq_item::type_id::create("tr");
    endfunction: build_phase

    virtual function void write(input {module_name}_seq_item t);
        /*
        tr = t;
        int expected_output;

        // Golden reference model
        {golden_reference_model}

        // Logic for comparision
        {verification_logic}
        tr.print()
        */
        // Additional comparison logic
        // User can add more comparison logic here
    endfunction
endclass: {module_name}_scoreboard
"""

def subscriber_gen(module_name, port_lst):
    """
    Function to generate the subscriber object file for coverages.
    parameters:
    module_name: The name of the design module.
    design_type: The 3rd command line argument. 
    """
    
    coverage_logic = ""

    for direction, width, port in port_lst:
        coverage_logic += f"\t{port.upper()}\t:\tcoverpoint {port};\n\t"

    return f"""
class {module_name}_subscribe extends uvm_subscribe #({module_name}_seq_item);
    `uvm_component_utils({module_name}_subscribe)

    {module_name}_seq_item req;

    real cov;

    // A basic coverpoint for all the signals. If needed, modify as per the needs.
    covergroup {module_name}_cg;
    option.per_instance = 2;
    {coverage_logic}endgroup: {module_name}_cg
    
    // Ad more additional covergroups with coverpoints here

    function new(input string name = {module_name}_subscribe, uvm_component parent = null);
        super.new(name, parent);

        req = {module_name}_seq_item::tyep_id::create("req");

        {module_name}_cd = new();

        //Create an object of your additional covergroup here.
    endfunction: new

    virtual function void write(input {module_name}_seq_item t);
        `uvm_info(get_type_name(), "Reading data from monitor for coverage", UVM_NONE);
        t.print;
        req = t;

        {module_name}.sample();
        cov = {module_name}.get_coverage();
        `uvm_info(get_full_name(), $sformatf("Coverage is %0d", cov), UVM_NONE);
    
    endfunction: write

endclass: {module_name}_subscribe
"""

def agent_gen(module_name):
    """
    Function to generate the agent object.
    parameters:
    module_name: The name of the design module.
    """
    
    return f"""
class {module_name}_agent extends uvm_agent;
    `uvm_component_utils({module_name}_agent)

    {module_name}_sequencer seqr;
    {module_name}_driver drv;
    {module_name}_monitor mon;

    function new(input string name = "{module_name}_agent", uvm_component parent = null);
        super.new(name, parent);
    endfunction: new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        seqr = {module_name}_sequencer::type_id::create("seqr", this);
        drv = {module_name}_driver::type_id::create("drv", this);
        mon = {module_name}_monitor::type_id::create("mon", this);
    endfunction: build_phase

    virtual function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);
        drv.seq_item_port.connect(seqr.seq_item_export);
    endfunction: connect_phase

endclass: {module_name}_agent
"""

def env_gen(module_name):
    """
    Function to generate the environment object.
    parameters:
    module_name: The name of the design module.
    """

    return f"""
class {module_name}_env extends uvm_env;
    `uvm_component_utils({module_name}_env)

    {module_name}_agent agnt;
    {module_name}_scoreboard sb;
   // {module_name}_subscribe subs;

    function new(input string name = "{module_name}_env", uvm_component parent = null);
        super.new(name, parent);
    endfunction

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        agnt = {module_name}_agent::type_id::create("agnt", this);
        sb = {module_name}_agent::type_id::create("sb", this); 
       // subs = {module_name}_subscribe::type_id::create("subs", this);    
    endfunction: build_phase

    virtual function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);
        agnt.mon.aport.connect(sb.aimport);
       // agnt.mon.aport.connect(subs.analysis_export);
    
    endfunction: connect_phase

endclass: {module_name}_env
"""

def test_gen(module_name):
    """
    Function to generate the test object.
    parameters:
    module_name: The name of the design module.
    """

    return f"""
class {module_name}_test extends uvm_test;
    `uvm_component_utils({module_name}_test)

    {module_name}_env env;
    {module_name}_seq seq;
    //declare your more sequences here if impemented.

    function new(input string name = "{module_name}_test", uvm_component parent = null);
        super.new(name, parent);
    endfunction: new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        env = {module_name}_env::type_id::create("env", this);
        seq = {module_name}_seq::type_id::create("seq", this);
    endfunction: build_phase

    virtual task run_phase(uvm_phase phase);
        phase.raise_objection(this);
            seq.start(env.agnt.seqr);
            #50;
        phase.drop_objection(this);
    endtask: run_phase

endclass: {module_name}_test
"""

def pkg_gen(module_name):
    """
    Function to generate the packages.
    parameters:
    module_name: The name of the design module.
    """

    return f"""
package {module_name}_pkg;
    import uvm_pkg::*;
    `include "uvm_macros.svh"
    `include "{module_name}_sequence_item.sv"
    `include "{module_name}_sequence.sv"
    `include "{module_name}_sequencer.sv"
    `include "{module_name}_driver.sv"
    `include "{module_name}_monitor.sv"
    `include "{module_name}_scoreboard.sv"
    `include "{module_name}_agent.sv"
    `include "{module_name}_env.sv"
    `include "{module_name}_test.sv"
endpackage
"""

def tb_gen(module_name, interface_name, port_lst):

    """
    Function to generate top level tb.
    parameters:
    module_name: The name of the design module.
    interface_name: interface name of the design. Used for config_db.
    """
    dut_instance_logic = ""
    i = 0
    for direction, width, port in port_lst:
        if (i < len(port_lst) - 1):
            dut_instance_logic += f".{port}(vif.{port}), \t\t\n"
        else: 
            dut_instance_logic += f".{port}(vif.{port}) \t\t\n"
        i += 1
    return f"""
module tb_{module_name};
    import uvm_pkg::*;
    import {module_name}_pkg::*;


    {interface_name} vif();
    {module_name} dut({dut_instance_logic});

    initial begin
        uvm_config_db#(virtual {interface_name})::set(null, "uvm_test_top.env.agent*", "vif", vif);
        run_test("{module_name}_test");
    end
endmodule
"""

def code_compilation(module_name):
    """
    Function to do the simulation check in Questa Sim ansd generate the coverage report in ucdb and convert it to txt.
    parameters:
    module_name: The name of the design module.
    """
    # Command to run the simulation using QuestaSim
    compile_cmd = f"vlog -sv {module_name}_pkg.sv {module_name}_tb.sv"
    run_cmd = f"vsim -coverage -vopt work.tb_{module_name} -c"
    run_cmd1 = f"run -all"
    run_cmd2 = f"coverage report -detail"

    try:
        subprocess.run(compile_cmd, shell=True, check=True)
        subprocess.run(run_cmd, shell=True, check=True)
        subprocess.run(run_cmd1, shell=True, check=True)
        subprocess.run(run_cmd2, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Simuilation Error: {e}")

def uvm_hierarchy(module_name):
    """
    Function to generate UVM hierarchy diagram.
    parameters:
    module_name: The name of the design module.
    """

    pdf_filename = f"{module_name}_uvm_hierarchy.pdf"
    c = canvas.Canvas(pdf_filename, pagesize=letter)
    width, height = letter

    positions = {
        'test': (width / 2, height - inch),
        'sequence_item': (width / 4, height - 2 * inch),
        'env': (3 * width / 4, height - 2 * inch),
        'scoreboard': (width / 6, height - 3 * inch),
        'agent': (width / 2, height - 3 * inch),
        'subscriber': (5 * width / 6, height - 3 * inch),
        'sequencer': (width / 4, height - 4 * inch),
        'driver': (width / 2, height - 4 * inch),
        'monitor': (3 * width / 4, height - 4 * inch),
    }
    
    box_width = 120
    box_height = 30
    for name, pos in positions.items():
        c.rect(pos[0] - box_width / 2, pos[1] - box_height / 2, box_width, box_height)
        c.drawString(pos[0] - box_width / 2 + 5, pos[1] - box_height / 4, f"{module_name}_{name}")

    connections = [
        ('test', 'sequence_item'),
        ('test', 'env'),
        ('env', 'scoreboard'),
        ('env', 'agent'),
        ('env', 'subscriber'),
        ('agent', 'sequencer'),
        ('agent', 'driver'),
        ('agent', 'monitor'),
    ]

    for start, end in connections:
        start_pos = positions[start]
        end_pos = positions[end]
        c.line(start_pos[0], start_pos[1] - box_height / 2, end_pos[0], end_pos[1] + box_height / 2)

    c.save()
    print(f"{pdf_filename} has been created")

def main():
    """
    The very main function that executes all the neccesary functions
    """

    # Check for the arguments entered in the console
    if (len(sys.argv) < 2 or len(sys.argv) > 3): 
        print("Argument syntax error. Please use the following pattern.\nUsage: python generate_uvm_tb.py <sv_module> <design_type>\nThe last argument is optional. Suppoted desgin type for this build: Adder, ALU ")
        sys.exit(1)

    # Declaring the first argument for SV design modules
    sv_module = sys.argv[1] 
    # Calling the function that will return Module name, ports with their respective width and directions, and interface name.
    module_name, ports, interface_name = design_scan(sv_module)
    
    #Check for 3rd argument that takes design type. If no 3rd argument, the basic framework will be selected
    if (len(sys.argv) == 3 and sys.argv[2].lower() == "run"):
        code_compilation(module_name)
        uvm_hierarchy(module_name)
    else:
        design_type = sys.argv[2] if len(sys.argv) == 3 else "basic_framework" 
        # The funntion responsible for generating UVM files
        uvm_framework_files_gen(module_name, ports, design_type, interface_name)

if __name__ == "__main__":
    main()
