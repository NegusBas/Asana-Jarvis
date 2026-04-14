import pyaudio
p = pyaudio.PyAudio()
print("\n------- AVAILABLE AUDIO DEVICES -------")
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        print(f"ID: {i} | Name: {info['name']}")
print("---------------------------------------\n")
p.terminate()


