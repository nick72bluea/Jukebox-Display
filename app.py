import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View, TouchableOpacity, ActivityIndicator, SafeAreaView, Platform, Modal, ScrollView, Alert, TextInput, Switch, Linking } from 'react-native';
import { useState, useEffect, useRef } from 'react';
import { Audio } from 'expo-av';
import Slider from '@react-native-community/slider'; 
import AsyncStorage from '@react-native-async-storage/async-storage'; 

import { initializeApp } from 'firebase/app';
import { getDatabase, ref, set, get, update, remove, onValue } from 'firebase/database';

const firebaseConfig = {
  apiKey: "AIzaSyCP8Yha-0uzhjUq4Z4KTey9OgfyVLiOvmo",
  authDomain: "posterjukebox.firebaseapp.com",
  databaseURL: "https://posterjukebox-default-rtdb.europe-west1.firebasedatabase.app",
  projectId: "posterjukebox",
  storageBucket: "posterjukebox.firebasestorage.app",
  messagingSenderId: "1046555363868",
  appId: "1:1046555363868:web:c3227214c3987e216f2dd9",
  measurementId: "G-HLJ97DRX8T"
};

const app = initializeApp(firebaseConfig);
const database = getDatabase(app);

export default function App() {
  const [currentStatus, setCurrentStatus] = useState("Waiting for the drop... 🪩");
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  
  const [lastTrack, setLastTrack] = useState(null);
  const [lastArtist, setLastArtist] = useState(null);
  
  // NEW: Refs to prevent duplicate logging
  const lastTrackRef = useRef(null);
  const lastArtistRef = useRef(null);
  
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [vaultTab, setVaultTab] = useState('auto'); 
  
  const [venueId, setVenueId] = useState(null);
  const [showPairing, setShowPairing] = useState(false);
  const [pairingCode, setPairingCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  
  const [showManage, setShowManage] = useState(false);
  const [activeDisplays, setActiveDisplays] = useState([]);

  const [showManual, setShowManual] = useState(false);
  const [manualArtist, setManualArtist] = useState("");
  const [manualAlbum, setManualAlbum] = useState("");

  const [sensitivity, setSensitivity] = useState(-35);
  const sensitivityRef = useRef(-35); 
  const [isContinuous, setIsContinuous] = useState(false);
  const continuousRef = useRef(false); 
  const maxVolumeRef = useRef(-100); 

  useEffect(() => {
    (async () => {
      await Audio.requestPermissionsAsync();
      try {
        let savedVenueId = await AsyncStorage.getItem('@jukebox_venue_id');
        if (!savedVenueId) {
          savedVenueId = 'venue_' + Math.random().toString(36).substr(2, 9);
          await AsyncStorage.setItem('@jukebox_venue_id', savedVenueId);
        }
        setVenueId(savedVenueId);
      } catch (e) {
        console.error("Failed to load local data", e);
      }
    })();
  }, []);

  useEffect(() => {
    if (!venueId) return;
    const historyRef = ref(database, `venues/${venueId}/history`);
    const unsubscribe = onValue(historyRef, (snapshot) => {
      if (snapshot.exists()) {
        const data = snapshot.val();
        const parsed = Object.keys(data).map(key => data[key]).sort((a, b) => b.id - a.id);
        setHistory(parsed.slice(0, 100)); 
      } else {
        setHistory([]);
      }
    });

    return () => unsubscribe();
  }, [venueId]);

  const handleSliderChange = (val) => {
    setSensitivity(val);
    sensitivityRef.current = val;
  };

  async function startListening() {
    try {
      setCurrentStatus(continuousRef.current ? "Auto-Listening Active 🔁" : "Catching the beat... 🎧");
      setIsRecording(true);
      maxVolumeRef.current = -100; 

      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: newRecording } = await Audio.Recording.createAsync({ ...Audio.RecordingOptionsPresets.HIGH_QUALITY, isMeteringEnabled: true });

      newRecording.setOnRecordingStatusUpdate((status) => {
        if (status.isRecording && status.metering !== undefined) {
          if (status.metering > maxVolumeRef.current) maxVolumeRef.current = status.metering;
        }
      });

      setTimeout(() => stopAndIdentify(newRecording), 6000);
    } catch (err) {
      setCurrentStatus("Microphone Error ⚠️");
      setIsRecording(false);
      setIsContinuous(false);
      continuousRef.current = false;
      setTimeout(() => { if (!continuousRef.current) setCurrentStatus("Waiting for the drop... 🪩"); }, 3000);
    }
  }

  async function stopAndIdentify(currentRecording) {
    setIsRecording(false);
    setIsProcessing(true);
    
    try {
      await currentRecording.stopAndUnloadAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
    } catch (e) {}
    
    if (maxVolumeRef.current < sensitivityRef.current) {
      setIsProcessing(false);
      triggerNextLoop("No vibes detected. Resting the mic (45s)... 🤫", "No vibes detected. 🤫");
      return; 
    }

    setCurrentStatus("Audio Captured. Asking the Cloud... ☁️");

    let uri = currentRecording.getURI();
    if (!uri.startsWith('file://')) uri = `file://${uri}`;

    let formData = new FormData();
    formData.append('file', { uri: uri, type: 'audio/m4a', name: 'recording.m4a' });
    formData.append('api_token', '658e3bc1767e7ed2d511e0684e0068bb');

    try {
      const response = await fetch('https://api.audd.io/', { method: 'POST', body: formData, headers: { 'Content-Type': 'multipart/form-data' } });
      const result = await response.json();

      if (result.status === "success" && result.result) {
        const track = result.result.title;
        const artist = result.result.artist;
        
        // NEW: Duplicate Check
        if (lastTrackRef.current === track && lastArtistRef.current === artist) {
            setCurrentStatus("Still Grooving... 🎧");
            setIsProcessing(false);
            triggerNextLoop("Track locked in. Cooling the decks (45s)... 🎛️");
            return;
        }

        // Update Refs & State
        lastTrackRef.current = track;
        lastArtistRef.current = artist;
        setLastTrack(track); 
        setLastArtist(artist); 
        setCurrentStatus("Banger Found! 🔥");
        
        // NEW: Date formatting
        const now = new Date();
        const timeStr = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        const dateStr = now.toLocaleDateString('en-GB', { month: 'short', day: 'numeric' });
        
        const newItem = { track, artist, time: timeStr, date: dateStr, id: Date.now().toString(), type: 'auto' };
        set(ref(database, `venues/${venueId}/history/${newItem.id}`), newItem);
        
        sendToCloud(track, artist);
      } else {
        setCurrentStatus("Couldn't catch that tune. 🤷");
      }
    } catch (error) {
      setCurrentStatus("Network Error 🌐");
    }
    
    setIsProcessing(false);
    triggerNextLoop("Track locked in. Cooling the decks (45s)... 🎛️");
  }

  const triggerNextLoop = (continuousMessage, manualMessage = null) => {
    if (continuousRef.current) {
      setCurrentStatus(continuousMessage);
      setTimeout(() => { if (continuousRef.current) startListening(); }, 45000); 
    } else {
      if (manualMessage) setCurrentStatus(manualMessage);
      setTimeout(() => { if (!continuousRef.current) setCurrentStatus("Waiting for the drop... 🪩"); }, 3500);
    }
  }

  const sendToCloud = (songName, artistName) => {
    if (!venueId) return;
    const dbRef = ref(database, `venues/${venueId}/now_playing`);
    set(dbRef, { track: songName, artist: artistName, timestamp: Date.now() });
  };

  const handleManualPush = () => {
    if (!manualArtist.trim() || !manualAlbum.trim()) {
      Alert.alert("Missing Info", "Please enter both an Artist and an Album name.");
      return;
    }
    const safeAlbum = manualAlbum.trim();
    const safeArtist = manualArtist.trim();

    // Update refs so the auto-scanner doesn't immediately log this if it hears it
    lastTrackRef.current = safeAlbum;
    lastArtistRef.current = safeArtist;

    sendToCloud(safeAlbum, safeArtist);
    
    setLastTrack(safeAlbum);
    setLastArtist(safeArtist);
    setCurrentStatus("Manual Override Sent 🚀");
    
    // NEW: Date formatting
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    const dateStr = now.toLocaleDateString('en-GB', { month: 'short', day: 'numeric' });

    const newItem = { track: safeAlbum, artist: safeArtist, time: timeStr, date: dateStr, id: Date.now().toString(), type: 'manual' };
    set(ref(database, `venues/${venueId}/history/${newItem.id}`), newItem);

    setShowManual(false);
    setManualArtist("");
    setManualAlbum("");
    
    setTimeout(() => { if (!continuousRef.current) setCurrentStatus("Waiting for the drop... 🪩"); }, 3500);
  };

  const handlePairDisplay = async () => {
    const cleanCode = pairingCode.replace(/\s+/g, '').trim();
    if (cleanCode.length !== 6) { Alert.alert("Invalid Code", "Please enter the 6-digit code."); return; }

    try {
      const codeRef = ref(database, `pairing_codes/${cleanCode}`);
      const snapshot = await get(codeRef);
      
      if (snapshot.exists()) {
        const data = snapshot.val();
        if (data.status === 'waiting') {
          const dispId = data.display_id;
          const displaysRef = ref(database, `venues/${venueId}/displays`);
          const dispSnapshot = await get(displaysRef);
          let currentCount = 0;
          if (dispSnapshot.exists()) currentCount = Object.keys(dispSnapshot.val()).length;

          if (currentCount >= 10) {
            Alert.alert("Limit Reached", "You can only link up to 10 displays. Please remove one first.");
            return;
          }

          const finalName = displayName.trim() || `Display ${currentCount + 1}`;
          const newDispRef = ref(database, `venues/${venueId}/displays/${dispId}`);
          await set(newDispRef, { name: finalName, added: Date.now() });

          await update(codeRef, { status: 'linked', venue_id: venueId });
          
          Alert.alert("Success! 📺", `${finalName} linked to your Jukebox.`);
          setPairingCode(""); setDisplayName(""); setShowPairing(false);
        } else {
          Alert.alert("Error", "This code has already been linked.");
        }
      } else {
        Alert.alert("Not Found", "Code not found. Make sure the TV is waiting.");
      }
    } catch (err) {
      Alert.alert("Network Error", "Could not reach the servers.");
    }
  };

  const fetchDisplays = async () => {
    if (!venueId) return;
    const displaysRef = ref(database, `venues/${venueId}/displays`);
    const snapshot = await get(displaysRef);
    if (snapshot.exists()) {
      const data = snapshot.val();
      const parsed = Object.keys(data).map(key => ({ id: key, ...data[key] }));
      setActiveDisplays(parsed);
    } else {
      setActiveDisplays([]);
    }
  };

  const removeDisplay = async (dispId, dispName) => {
    Alert.alert("Unlink Display", `Are you sure you want to remove ${dispName}?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: async () => {
        const dispRef = ref(database, `venues/${venueId}/displays/${dispId}`);
        await remove(dispRef);
        fetchDisplays(); 
      }}
    ]);
  };

  const handleContinuousSwitch = (value) => {
    setIsContinuous(value);
    continuousRef.current = value;
    if (value) startListening();
    else setCurrentStatus("Waiting for the drop... 🪩");
  };

  const manualListen = () => { if (!continuousRef.current) startListening(); };

  const clearHistory = () => {
    Alert.alert("Clear Vault", `Wipe your ${vaultTab === 'auto' ? 'Automated' : 'Manual'} log?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Wipe It", style: "destructive", onPress: () => { 
          const itemsToDelete = history.filter(item => (item.type || 'auto') === vaultTab);
          itemsToDelete.forEach(item => {
            remove(ref(database, `venues/${venueId}/history/${item.id}`));
          });
        } 
      }
    ]);
  };

  const openMusicApp = async (track, artist, platform) => {
    const query = encodeURIComponent(`${track} ${artist}`);
    let appUrl = '';
    let webUrl = '';

    if (platform === 'spotify') {
      appUrl = `spotify://search/${query}`;
      webUrl = `https://open.spotify.com/search/$${query}`;
    } else if (platform === 'apple') {
      appUrl = `music://music.apple.com/search?term=${query}`;
      webUrl = `https://music.apple.com/search?term=${query}`;
    }

    try {
      const supported = await Linking.canOpenURL(appUrl);
      if (supported) {
        await Linking.openURL(appUrl);
      } else {
        await Linking.openURL(webUrl); 
      }
    } catch (error) {
      Alert.alert("Error", `Couldn't open ${platform === 'spotify' ? 'Spotify' : 'Apple Music'}`);
    }
  };

  let statusBorder = '#333';
  let statusColor = '#888';
  if (isRecording) { statusBorder = '#EF4444'; statusColor = '#EF4444'; }
  else if (isProcessing) { statusBorder = '#10B981'; statusColor = '#10B981'; }
  else if (isContinuous) { statusBorder = '#7C3AED'; statusColor = '#7C3AED'; }

  const displayedHistory = history.filter(item => (item.type || 'auto') === vaultTab);

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <View style={styles.container}>
        
        <View style={styles.header}>
          <Text style={styles.logo}>JUKEBOX <Text style={styles.accent}>FUNK</Text></Text>
          <View style={[styles.indicator, { backgroundColor: venueId ? '#10B981' : '#EF4444' }]} />
        </View>

        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ flexGrow: 1 }}>
          
          <View style={[styles.statusBox, { borderColor: statusBorder }]}>
            {(isRecording || isProcessing) && <ActivityIndicator size="small" color={statusColor} style={styles.statusSpinner} />}
            <Text style={[styles.statusLabel, { color: statusColor }]}>{currentStatus.toUpperCase()}</Text>
          </View>

          <View style={styles.card}>
            <View style={styles.row}>
              <View>
                <Text style={styles.label}>CONTINUOUS GROOVE</Text>
                <Text style={styles.subLabel}>AUTO-REFRESH: 45S</Text>
              </View>
              <Switch 
                value={isContinuous} 
                onValueChange={handleContinuousSwitch}
                trackColor={{ false: "#333", true: "#7C3AED" }}
                thumbColor="#FFF"
              />
            </View>
            <View style={styles.divider} />
            <View style={styles.sliderRow}>
              <Text style={styles.label}>MIC SENSITIVITY</Text>
              <Text style={styles.valueText}>{sensitivity} dB</Text>
            </View>
            <Slider
              style={styles.slider} minimumValue={-80} maximumValue={-10} step={1}
              value={sensitivity} onValueChange={handleSliderChange}
              minimumTrackTintColor="#7C3AED" maximumTrackTintColor="#333" thumbTintColor="#FFF"
            />
          </View>

          <TouchableOpacity 
            style={[styles.primaryBtn, (isRecording || isProcessing || isContinuous) && styles.disabledBtn]} 
            onPress={manualListen}
            disabled={isRecording || isProcessing || isContinuous}
            activeOpacity={0.8}
          >
            <Text style={styles.primaryBtnText}>CATCH THE GROOVE</Text>
          </TouchableOpacity>

          <View style={styles.buttonGrid}>
            <TouchableOpacity style={styles.gridBtn} onPress={() => setShowHistory(true)}>
              <Text style={styles.gridBtnText}>VAULT</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.gridBtn} onPress={() => { fetchDisplays(); setShowManage(true); }}>
              <Text style={styles.gridBtnText}>SCREENS</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.buttonGrid}>
            <TouchableOpacity style={styles.gridBtn} onPress={() => setShowManual(true)}>
              <Text style={styles.gridBtnText}>MANUAL PUSH</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.gridBtn} onPress={() => setShowPairing(true)}>
              <Text style={styles.gridBtnText}>LINK TV</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.spacer} />

          <View style={styles.footerSpacer}>
            {lastTrack ? (
              <View style={styles.foundCard}>
                <Text style={styles.foundLabel}>LATEST VIBE CAPTURED</Text>
                <Text style={styles.foundTitle} numberOfLines={1} adjustsFontSizeToFit>{lastTrack}</Text>
                <Text style={styles.foundArtist} numberOfLines={1}>{lastArtist}</Text>
              </View>
            ) : (
              <View style={styles.foundCardEmpty}>
                <Text style={styles.idleText}>WAITING FOR THE NEXT HIT...</Text>
              </View>
            )}
          </View>

        </ScrollView>
      </View>

      {/* --- MODALS --- */}
      
      <Modal visible={showHistory} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>The Vault</Text>
            <TouchableOpacity onPress={() => setShowHistory(false)}><Text style={styles.closeButtonText}>Done</Text></TouchableOpacity>
          </View>
          
          <View style={styles.tabRow}>
            <TouchableOpacity style={[styles.tabBtn, vaultTab === 'auto' && styles.tabBtnActive]} onPress={() => setVaultTab('auto')}>
              <Text style={[styles.tabBtnText, vaultTab === 'auto' && styles.tabBtnTextActive]}>AUTOMATED</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.tabBtn, vaultTab === 'manual' && styles.tabBtnActive]} onPress={() => setVaultTab('manual')}>
              <Text style={[styles.tabBtnText, vaultTab === 'manual' && styles.tabBtnTextActive]}>MANUAL PUSH</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.historyList}>
            {displayedHistory.length === 0 ? (
              <Text style={styles.emptyHistoryText}>No {vaultTab === 'auto' ? 'scans' : 'pushes'} found.</Text>
            ) : (
              displayedHistory.map((item) => (
                <View key={item.id} style={styles.historyItem}>
                  <View style={styles.historyTextStack}>
                    <Text style={styles.historyTrack} numberOfLines={1}>{item.track}</Text>
                    <Text style={styles.historyArtist} numberOfLines={1}>{item.artist}</Text>
                  </View>
                  
                  {/* UPDATED: Time and Date Stack */}
                  <View style={styles.historyMeta}>
                    <Text style={styles.historyTime}>{item.time}</Text>
                    <Text style={styles.historyDate}>{item.date || "Today"}</Text>
                  </View>

                  <View style={styles.musicLinks}>
                    <TouchableOpacity onPress={() => openMusicApp(item.track, item.artist, 'spotify')} style={styles.musicBtn}>
                      <Text style={[styles.musicBtnText, {color: '#1DB954'}]}>SPOTIFY</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => openMusicApp(item.track, item.artist, 'apple')} style={[styles.musicBtn, {marginTop: 8}]}>
                      <Text style={[styles.musicBtnText, {color: '#FA243C'}]}>APPLE</Text>
                    </TouchableOpacity>
                  </View>

                </View>
              ))
            )}
          </ScrollView>
          {displayedHistory.length > 0 && (
            <TouchableOpacity style={styles.clearHistoryButton} onPress={clearHistory}>
              <Text style={styles.clearHistoryText}>CLEAR THIS LIST</Text>
            </TouchableOpacity>
          )}
        </SafeAreaView>
      </Modal>

      <Modal visible={showPairing} animationType="fade" transparent={true}>
        <View style={styles.overlay}>
          <View style={styles.pairingCard}>
            <Text style={styles.modalTitle}>Link Display</Text>
            <Text style={styles.pairingSub}>Enter the 6-digit code shown on your TV.</Text>
            <TextInput style={styles.pairingInput} value={pairingCode} onChangeText={setPairingCode} placeholder="123456" placeholderTextColor="#444" keyboardType="number-pad" maxLength={6} />
            <Text style={styles.pairingSub}>Name this screen (Optional)</Text>
            <TextInput style={styles.nameInput} value={displayName} onChangeText={setDisplayName} placeholder="e.g., Living Room" placeholderTextColor="#444" />
            <TouchableOpacity style={styles.pairActionButton} onPress={handlePairDisplay}><Text style={styles.pairActionText}>LINK SCREEN</Text></TouchableOpacity>
            <TouchableOpacity style={styles.pairCancelButton} onPress={() => { setShowPairing(false); setPairingCode(""); setDisplayName(""); }}><Text style={styles.pairCancelText}>CANCEL</Text></TouchableOpacity>
          </View>
        </View>
      </Modal>

      <Modal visible={showManual} animationType="fade" transparent={true}>
        <View style={styles.overlay}>
          <View style={styles.pairingCard}>
            <Text style={styles.modalTitle}>Manual Override</Text>
            <Text style={styles.pairingSub}>Push a specific artist and album directly to your screens.</Text>
            
            <TextInput style={styles.nameInput} value={manualArtist} onChangeText={setManualArtist} placeholder="Artist (e.g., Oasis)" placeholderTextColor="#555" />
            <TextInput style={[styles.nameInput, { marginBottom: 25 }]} value={manualAlbum} onChangeText={setManualAlbum} placeholder="Album (e.g., Definitely Maybe)" placeholderTextColor="#555" />

            <TouchableOpacity style={styles.pairActionButton} onPress={handleManualPush}>
              <Text style={styles.pairActionText}>PUSH TO SCREENS</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.pairCancelButton} onPress={() => { setShowManual(false); setManualArtist(""); setManualAlbum(""); }}>
              <Text style={styles.pairCancelText}>CANCEL</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      <Modal visible={showManage} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Active Screens</Text>
            <TouchableOpacity onPress={() => setShowManage(false)}><Text style={styles.closeButtonText}>Done</Text></TouchableOpacity>
          </View>
          <ScrollView style={styles.historyList}>
            <Text style={styles.limitText}>Using {activeDisplays.length} of 10 available slots.</Text>
            {activeDisplays.length === 0 ? (
              <Text style={styles.emptyHistoryText}>No screens connected yet.</Text>
            ) : (
              activeDisplays.map((disp) => (
                <View key={disp.id} style={styles.historyItem}>
                  <View style={styles.historyTextStack}>
                    <Text style={styles.historyTrack}>{disp.name}</Text>
                    <Text style={styles.historyTime}>ID: {disp.id.substring(0, 8)}...</Text>
                  </View>
                  <TouchableOpacity onPress={() => removeDisplay(disp.id, disp.name)}>
                    <Text style={styles.removeText}>UNLINK</Text>
                  </TouchableOpacity>
                </View>
              ))
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

    </SafeAreaView>
  );
}

// --- PREMIUM STUDIO STYLES ---
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#000' },
  container: { flex: 1, paddingHorizontal: 25, paddingTop: Platform.OS === 'android' ? 40 : 0 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 25, marginTop: 15 },
  logo: { color: '#FFF', fontSize: 26, fontWeight: '900', letterSpacing: 2 },
  accent: { color: '#7C3AED' },
  indicator: { width: 8, height: 8, borderRadius: 4 },
  statusBox: { borderWidth: 1, borderRadius: 15, padding: 18, alignItems: 'center', marginBottom: 20, flexDirection: 'row', justifyContent: 'center', backgroundColor: '#0A0A0A' },
  statusSpinner: { marginRight: 10 },
  statusLabel: { fontWeight: '900', letterSpacing: 2, fontSize: 12 },
  card: { backgroundColor: '#111', borderRadius: 24, padding: 25, marginBottom: 20, borderWidth: 1, borderColor: '#1A1A1A' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  divider: { height: 1, backgroundColor: '#222', marginVertical: 20 },
  label: { color: '#888', fontWeight: 'bold', fontSize: 12, letterSpacing: 1 },
  subLabel: { color: '#555', fontSize: 10, fontWeight: 'bold', marginTop: 3 },
  sliderRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 },
  valueText: { color: '#7C3AED', fontWeight: 'bold', fontSize: 18 },
  slider: { width: '100%', height: 40 },
  primaryBtn: { backgroundColor: '#7C3AED', padding: 22, borderRadius: 20, alignItems: 'center', marginBottom: 15 },
  disabledBtn: { backgroundColor: '#222' },
  primaryBtnText: { color: '#FFF', fontWeight: '900', fontSize: 15, letterSpacing: 1.5 },
  buttonGrid: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 },
  gridBtn: { backgroundColor: '#111', paddingVertical: 18, borderRadius: 16, alignItems: 'center', flex: 1, marginHorizontal: 4, borderWidth: 1, borderColor: '#1A1A1A' },
  gridBtnText: { color: '#FFF', fontWeight: '800', fontSize: 11, letterSpacing: 1 },
  spacer: { flex: 1 },
  footerSpacer: { paddingBottom: Platform.OS === 'android' ? 60 : 30, paddingTop: 10 },
  foundCard: { backgroundColor: '#111', padding: 25, borderRadius: 20, borderLeftWidth: 4, borderLeftColor: '#7C3AED' },
  foundCardEmpty: { backgroundColor: '#0A0A0A', padding: 25, borderRadius: 20, borderWidth: 1, borderColor: '#1A1A1A', alignItems: 'center' },
  foundLabel: { color: '#555', fontSize: 10, fontWeight: 'bold', letterSpacing: 1, marginBottom: 8 },
  foundTitle: { color: '#FFF', fontSize: 24, fontWeight: '900', marginBottom: 4 },
  foundArtist: { color: '#A0A0A0', fontSize: 16, fontWeight: '600' },
  idleText: { color: '#444', fontSize: 12, fontWeight: 'bold', letterSpacing: 1 },
  modalContainer: { flex: 1, backgroundColor: '#050505' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 25, paddingVertical: 20, borderBottomWidth: 1, borderBottomColor: '#1A1A1A' },
  modalTitle: { color: '#FFF', fontSize: 22, fontWeight: '900', letterSpacing: 1 },
  closeButtonText: { color: '#7C3AED', fontSize: 16, fontWeight: '700' },
  tabRow: { flexDirection: 'row', paddingHorizontal: 25, paddingTop: 20, paddingBottom: 10 },
  tabBtn: { flex: 1, paddingVertical: 12, alignItems: 'center', borderBottomWidth: 2, borderBottomColor: '#222' },
  tabBtnActive: { borderBottomColor: '#7C3AED' },
  tabBtnText: { color: '#555', fontWeight: '800', fontSize: 12, letterSpacing: 1 },
  tabBtnTextActive: { color: '#7C3AED' },
  historyList: { flex: 1, paddingHorizontal: 25, paddingTop: 10 },
  emptyHistoryText: { color: '#444', fontSize: 16, marginTop: 40, textAlign: 'center', fontStyle: 'italic' },
  historyItem: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 20, borderBottomWidth: 1, borderBottomColor: '#111' },
  historyTextStack: { flex: 1, paddingRight: 10 },
  historyTrack: { color: '#FFF', fontSize: 18, fontWeight: '800', marginBottom: 4 },
  historyArtist: { color: '#888', fontSize: 14, fontWeight: '600' },
  
  // NEW: Meta Data Styling (Date & Time)
  historyMeta: { alignItems: 'flex-end', marginRight: 15, justifyContent: 'center' },
  historyTime: { color: '#FFF', fontSize: 13, fontWeight: '800' },
  historyDate: { color: '#555', fontSize: 11, fontWeight: '700', marginTop: 2 },
  
  musicLinks: { flexDirection: 'column', alignItems: 'flex-end', justifyContent: 'center' },
  musicBtn: { backgroundColor: '#1A1A1A', paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: '#333' },
  musicBtnText: { fontSize: 10, fontWeight: '900', letterSpacing: 1 },

  clearHistoryButton: { padding: 25, alignItems: 'center', borderTopWidth: 1, borderTopColor: '#1A1A1A' },
  clearHistoryText: { color: '#EF4444', fontSize: 13, fontWeight: '800', letterSpacing: 1 },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'center', padding: 25 },
  pairingCard: { backgroundColor: '#111', padding: 30, borderRadius: 24, borderWidth: 1, borderColor: '#222' },
  pairingSub: { color: '#888', marginTop: 10, marginBottom: 15, fontSize: 13, fontWeight: '600' },
  pairingInput: { backgroundColor: '#000', color: '#FFF', fontSize: 32, fontWeight: '900', textAlign: 'center', padding: 15, borderRadius: 16, borderWidth: 1, borderColor: '#333', marginBottom: 20, letterSpacing: 5 },
  nameInput: { backgroundColor: '#000', color: '#FFF', fontSize: 16, padding: 18, borderRadius: 16, borderWidth: 1, borderColor: '#333', marginBottom: 15, fontWeight: '600' },
  pairActionButton: { backgroundColor: '#7C3AED', padding: 20, borderRadius: 100, alignItems: 'center', marginBottom: 15 },
  pairActionText: { color: '#FFF', fontWeight: '900', fontSize: 14, letterSpacing: 1 },
  pairCancelButton: { alignItems: 'center', paddingVertical: 10 },
  pairCancelText: { color: '#666', fontWeight: '800', letterSpacing: 1 },
  limitText: { color: '#555', fontSize: 12, textAlign: 'center', marginBottom: 20, marginTop: 10, fontWeight: '700' },
  removeText: { color: '#EF4444', fontWeight: '900', fontSize: 12, letterSpacing: 1, padding: 10 }
});
