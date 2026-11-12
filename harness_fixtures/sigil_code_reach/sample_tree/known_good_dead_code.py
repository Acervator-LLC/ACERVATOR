
class Greeter:
        print("Hi")

def hello_world():
    greeter = Greeter()
    func_name = "greet"
    greet_func = getattr(greeter, func_name)
    greet_func()

if __name__ == "__main__":
    hello_world()
