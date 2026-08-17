import test_contracts


def main():
    tests = [name for name in dir(test_contracts)
             if name.startswith("test_")]
    for name in sorted(tests):
        getattr(test_contracts, name)()
        print(f"PASS {name}")
    print(f"{len(tests)} contract tests passed")


if __name__ == "__main__":
    main()
