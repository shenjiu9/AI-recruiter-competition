def run_once(container):
    with container.scope() as s:
        s.interview.tick()
