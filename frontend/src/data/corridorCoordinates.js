// RED LINE: Miyapur -> LB Nagar (27 stations)
export const RED_LINE_COORDS = [
  [17.4965, 78.3730],  // Miyapur
  [17.4987, 78.3889],  // JNTU
  [17.4938, 78.4018],  // KPHB Colony
  [17.4849, 78.4118],  // Kukatpally
  [17.4767, 78.4221],  // Balanagar
  [17.4719, 78.4261],  // Moosapet
  [17.4629, 78.4305],  // Bharat Nagar
  [17.4549, 78.4328],  // Erragadda
  [17.4459, 78.4418],  // ESI Hospital
  [17.4402, 78.4477],  // SR Nagar
  [17.4365, 78.4537],  // Ameerpet (interchange)
  [17.4324, 78.4600],  // Punjagutta
  [17.4258, 78.4635],  // Irrum Manzil
  [17.4180, 78.4695],  // Khairatabad
  [17.4095, 78.4730],  // Lakdi-ka-pul
  [17.4037, 78.4742],  // Assembly
  [17.3958, 78.4790],  // Nampally
  [17.3873, 78.4822],  // Gandhi Bhavan
  [17.3815, 78.4861],  // Osmania Medical College
  [17.3798, 78.4923],  // MG Bus Station
  [17.3729, 78.4972],  // Malakpet
  [17.3665, 78.5040],  // New Market
  [17.3613, 78.5110],  // Musarambagh
  [17.3569, 78.5174],  // Dilsukhnagar
  [17.3524, 78.5231],  // Chaitanyapuri
  [17.3470, 78.5291],  // Victoria Memorial
  [17.3434, 78.5356],  // LB Nagar
];

// BLUE LINE: Nagole -> Raidurg (24 stations)
export const BLUE_LINE_COORDS = [
  [17.3931, 78.5567],  // Nagole
  [17.3975, 78.5470],  // Uppal
  [17.4021, 78.5360],  // Stadium
  [17.4070, 78.5252],  // NGRI
  [17.4114, 78.5143],  // Habsiguda
  [17.4143, 78.5045],  // Tarnaka
  [17.4185, 78.4959],  // Mettuguda  
  [17.4220, 78.4869],  // Secunderabad East
  [17.4282, 78.4771],  // Parade Ground
  [17.4344, 78.4687],  // Paradise
  [17.4365, 78.4537],  // Ameerpet (interchange)
  [17.4364, 78.4438],  // Madhura Nagar
  [17.4382, 78.4342],  // Yousufguda
  [17.4403, 78.4245],  // Road No 5 Jubilee Hills
  [17.4426, 78.4153],  // Jubilee Hills Checkpost
  [17.4452, 78.4053],  // Peddamma Temple
  [17.4468, 78.3961],  // Madhapur
  [17.4479, 78.3877],  // Durgam Cheruvu
  [17.4455, 78.3808],  // HITEC City
  [17.4427, 78.3735],  // Raidurg
];

// GREEN LINE: JBS -> MGBS (7 stations)
export const GREEN_LINE_COORDS = [
  [17.4445, 78.4976],  // JBS Parade Ground
  [17.4425, 78.4950],  // Secunderabad West
  [17.4375, 78.4920],  // Gandhi Hospital
  [17.4340, 78.4890],  // Musheerabad
  [17.4280, 78.4860],  // RTC Cross Roads
  [17.4190, 78.4850],  // Chikkadpally
  [17.4050, 78.4840],  // Narayanguda
  [17.3878, 78.4862],  // Sultan Bazaar  
  [17.3798, 78.4923],  // MG Bus Station
];

// Station IDs mapped along each line in order
export const RED_LINE_STATIONS = ['MYP','JNT','KPH','KUK','BLR','MSP','BTN','ERG','ESI','SRN','AME','PJG','IRU','KHR','LKP','ASM','NAM','GBV','OMC','MGB','MLK','NMK','MSR','DLK','CTP','VCM','LBN'];
export const BLUE_LINE_STATIONS = ['NAG','UPL','STD','NGR','HAB','TNK','MTG','SBD','PDG','PRD','AME','MDN','YSG','RD5','JHC','PED','MAD','DGC','HTC','RDG'];
export const GREEN_LINE_STATIONS = ['JBS','SBW','GHO','MSH','RTC','CKD','NRY','SLB','MGB'];

export const CORRIDOR_META = {
  RED:   { color: '#E31E24', glow: 'rgba(227, 30, 36, 0.6)',  name: 'Red Line',   from: 'Miyapur', to: 'LB Nagar', coords: RED_LINE_COORDS, stations: RED_LINE_STATIONS },
  BLUE:  { color: '#007ABB', glow: 'rgba(0, 122, 187, 0.6)',  name: 'Blue Line',  from: 'Nagole',  to: 'Raidurg',  coords: BLUE_LINE_COORDS, stations: BLUE_LINE_STATIONS },
  GREEN: { color: '#009846', glow: 'rgba(0, 152, 70, 0.6)',   name: 'Green Line', from: 'JBS',     to: 'MGBS',     coords: GREEN_LINE_COORDS, stations: GREEN_LINE_STATIONS },
};
