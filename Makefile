all: demo/starwash-128k-2250.tzx demo/starwash-48k-2250.tzx

demo/starwash-128k-2250.tzx:
	./turbo_tap.py --baud 2250 demo/starwash-128k.tap demo starwash-128k-2250
	./turbo_tap.py --baud 3000 demo/starwash-128k.tap demo starwash-128k-3000
	./turbo_tap.py --baud 3500 demo/starwash-128k.tap demo starwash-128k-3500
	./turbo_tap.py --baud 4150 demo/starwash-128k.tap demo starwash-128k-4150

demo/starwash-48k-2250.tzx:
	./turbo_tap.py --baud 2250 demo/starwash-48k.tap demo starwash-48k-2250

clean:
	-rm demo/*.tzx

