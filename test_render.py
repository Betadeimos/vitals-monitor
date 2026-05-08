import vitals

def test():
    metrics = {'cpu_percent': 10.0, 'memory_gb': 1.0, 'priority': 32, 'cpu_affinity': [0, 1]}
    print("Testing legacy render_ui...")
    output = vitals.render_ui(metrics, state=vitals.NORMAL)
    print(output)

test()
