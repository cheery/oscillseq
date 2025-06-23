SequencerLib {
	*setup { |server, busTable, play, stop|
		var buses, instruments;
		buses        = IdentityDictionary.new;
		instruments  = IdentityDictionary.new;

		busTable.keysValuesDo { |key, val|
			var sym = key.asSymbol;
			buses[sym] = (
				bus: val,
				//buffer: Buffer.alloc(server, 100),
				syn: nil
			);
		};

		SynthDef(\quadraticFunc, { |out, a=0.0, b=0.0, c=0.0, t=0.0|
			var x = Sweep.kr(\trig.tr(0)).min(t);
			var val = (a*x*x) + (b*x) + c;
			Out.kr(out, val);
		}).add;

		/*
		SynthDef(\bufControl, { |out, buf, dur = 0.1|
			var frames = BufFrames.ir(buf);

			var idx = Phasor.kr(
				trig: \trig.tr(0),
				rate: 0.5 / dur,
				start: 0,
				end: frames * 2
			);
			var val = BufRd.kr(1, buf, idx, loop:0);
			Out.kr(out, val);
		}).add;
		*/

		OSCdef(\record, { |msg|
			var path = msg[1].asString, format = msg[2], duration = msg[3];
			server.recHeaderFormat = format;
			server.record(path: path, duration: duration);

			buses.keysValuesDo { |key, handle|
				handle.syn = Synth(\quadraticFunc, [
				out: handle.bus
				//buf: handle.buffer,
				//dur: 0.1], addAction: \addBefore);
				], addAction: \addBefore);
			};

			play.value;
		}, '/transport/record');

		OSCdef(\play, {
			buses.keysValuesDo { |key, handle|
				handle.syn = Synth(\quadraticFunc, [
				out: handle.bus
				//buf: handle.buffer,
				//dur: 0.1], addAction: \addBefore);
				], addAction: \addBefore);
			};

			play.value;
		}, '/transport/play');

		OSCdef(\stop, {
			stop.value;
			instruments.clear;
		}, '/transport/stop');

		OSCdef(\busSet, { |msg|
			var id = msg[1].asSymbol,
			    a  = msg[2],
			    b  = msg[3],
			    c  = msg[4],
			    t  = msg[5];
			var handle = buses[id];
			if (handle.notNil, {
				handle.syn.set(\trig, 1, \a, a, \b, b, \c, c, \t, t);
			});
			/*
			var id = msg[1].asSymbol,
			    vals = msg.asArray.drop(2).asFloat,
			    handle = buses[id];
			if (handle.notNil, {
				handle.buffer.setn(0, vals);
				handle.synth.set(\trig, 1);
			});*/
		}, '/bus/set');

		OSCdef(\oneShot, { |msg|
			var eventID = msg[1].asSymbol, args = msg.copyRange(2, msg.size-1);
			Synth(eventID, args);
		}, '/instrument/oneshot');

		OSCdef(\instTrig, { |msg|
			var instID = msg[1].asSymbol, idx = msg[2], args = msg.copyRange(3, msg.size-1);
			if(instruments[instID].isNil, {
				instruments[instID] = IdentityDictionary.new;
			});
			instruments[instID][idx] = Synth(instID, args);
		}, '/instrument/trigger');

		OSCdef(\instCtrl, { |msg|
			var instID = msg[1].asSymbol, idx = msg[2], args = msg.copyRange(3, msg.size-1);
			instruments[instID][idx].set(*args);
		}, '/instrument/control');

		OSCdef(\instRel, { |msg|
			var instID = msg[1].asSymbol, idx = msg[2], args = msg.copyRange(3, msg.size-1);
			instruments[instID][idx].set(*args);
			instruments[instID][idx].release;
			instruments[instID].removeAt(idx);
		}, '/instrument/release');

		nil
	}
}