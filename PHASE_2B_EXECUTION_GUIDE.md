# Phase 2B Execution Guide
## Manual Configuration Steps for AnyLogic

**Status:** Ready for manual AnyLogic configuration  
**System Status:** AnyLogic not currently running (needs to be opened on your machine)  
**Date:** April 14, 2026

---

## 📋 What Needs to be Done

You need to manually configure Agent Population in AnyLogic. This is a **3-step GUI procedure** that takes about 5 minutes.

### The Core Problem
Currently in the `uav-maritime-twin1.alp` project:
- ✅ Vessel agent type is defined
- ✅ GIS space is configured  
- ✅ Database is imported
- ❌ **MISSING:** Vessel population registration in Main agent's GIS space

This missing registration is why the error occurs: `"The method add_Vessel() is undefined"`

---

## 🚀 STEP-BY-STEP: Register Vessel Population

### Prerequisites
- Open AnyLogic on your computer
- Open the project file: `uav-maritime-twin1/uav-maritime-twin1.alp`

### Procedure

#### STEP 1: Access Main Agent Properties
1. In AnyLogic, locate the **"Model"** tree on the left panel
2. Find and expand the "Main" agent entry
3. Right-click "Main" → Select **"Properties"**
   - Alternative: Double-click "Main" → Click "Properties" button

#### STEP 2: Navigate to "Space and network" Section
1. In the Main agent Properties window that opens:
2. Look for the section: **"Space and network"**
3. Under this section, find: **"Agents in the space"** field
4. This field should be empty or show a small table

#### STEP 3: Add Vessel Population
1. In the "Agents in the space" table:
2. Click **"Add"** button (usually a "+" button)
3. A dialog will appear asking you to select an agent type
4. **Select: "Vessel"** from the dropdown/list
5. Accept default settings (population name will auto-populate as "Vessel")
6. Click **OK**

#### Result
You should now see "Vessel" listed in the "Agents in the space" table.

### STEP 4: Verify & Save
1. Click **OK** to close Properties dialog
2. **File → Save** (Ctrl+S or Cmd+S)
3. Close and reopen the project to apply changes

---

## ✅ How to Verify It Worked

After completing the above steps, the error should be fixed. Test by:

1. Open the Main agent's **"On Startup"** code section
2. Replace the current code with:
```java
traceln("Creating test vessel...");
Vessel v = add_Vessel();
v.latitude = 22.28;
v.longitude = 114.09;
v.speed = 5.0;
traceln("Vessel created: " + Vessel.all.size());
```

3. Run the simulation → Check console for output
4. Expected output: `"Vessel created: 1"`

---

## 🔧 If You Get Different Errors

### Error: "Cannot find variable Vessels" or "vessels is undefined"
This is **database access issue** (Phase 2B Step 2). Solution:
- Try using capitalized name: `Vessels` instead of `vessels`
- Or use: `getDatabase().getTable("vessels")`

### Error: "GIS space not properly configured"  
This shouldn't happen since Phase 2A validated it, but if it does:
- Verify EnvironmentProperties → SpaceType = "GIS"
- Verify coordinate system: Latitude/Longitude (Hong Kong: 22.2-22.4°N, 114.0-114.3°E)

### The property window shows different field names
This depends on your AnyLogic version. Look for:
- "Populations" or "Agents in space" or "Agent types in this space"
- The concept is the same - you're registering which agent types exist in Main's space

---

## 📝 Configuration Details

### Population Name
- **Default:** Vessel  
- **Array name:** Vessel (for accessing all instances)
- **Add method:** add_Vessel() (for creating new instance)
- **All instances:** Vessel.all (for iterating all agents)

### Population Scope
- **Scope:** Main agent's GIS space
- **Type:** Dynamic population (agents created/destroyed at runtime)
- **Initial count:** 0 (you create them in startup code)

---

## 🎯 Next: After Population is Registered

Once you've registered the Vessel population and saved, proceed to **Phase 2B Step 2** (Fix Database Access):

Replace the "On Startup" code with:
```java
// Try approach 1 (most likely to work)
for(int i = 0; i < Vessels.size(); i++) {
    Vessel v = add_Vessel();
    v.vessel_id = Vessels.get(i, "vessel_id") + "";
    v.latitude = (double) Vessels.get(i, "latitude");
    v.longitude = (double) Vessels.get(i, "longitude");
    v.speed = (double) Vessels.get(i, "speed");
}
traceln("Loaded " + Vessel.all.size() + " vessels from database");
```

If that fails, see the PHASE_2B_INITIALIZATION.md file for alternative database access methods.

---

## 🎬 Quick Reference: AnyLogic GUI Navigation

```
Project open in AnyLogic
  ↓
Model tree (left panel) → Main agent
  ↓
Right-click Main → Properties
  ↓
Properties window → Space and network section
  ↓
"Agents in the space" field → Click Add
  ↓
Select "Vessel" from list
  ↓
OK → OK
  ↓
File → Save
```

---

## ⏱️ Time Estimate
- Population registration: 3-5 minutes
- Database access troubleshooting: 5-10 minutes  
- Verification & testing: 5-10 minutes
- **Total Phase 2B:** 15-30 minutes

---

## 💾 File Locations
- **Project file:** `/sessions/eager-adoring-hopper/mnt/uav-maritime-twin/uav-maritime-twin1/uav-maritime-twin1.alp`
- **Database:** `maritime_baseline_24h.xlsx` (already imported)
- **Fairways:** `data/FairywayTSSrevised_converted.geojson` (already loaded)

---

**Once you complete the population registration in AnyLogic, return here and we'll proceed with Step 2: Database access configuration.**
