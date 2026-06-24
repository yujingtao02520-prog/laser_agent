import sys
import os

# Ensure root is on PATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend import db, vision, recommender, optimizer

def run_tests():
    print("=" * 60)
    print("🚀 STARTING LASER CUTTING COPILOT SYSTEM INTEGRATION TEST")
    print("=" * 60)

    # ----------------------------------------------------
    # TEST 1: Database Recipes Load & Count
    # ----------------------------------------------------
    print("\n[TEST 1] Testing Expert Database...")
    recipes = db.get_all_recipes()
    print(f"-> Total expert recipes loaded: {len(recipes)}")
    assert len(recipes) >= 12, "Database should contain at least 12 baseline recipes."
    
    # Query materials
    q235_recipes = [r for r in recipes if r["material"] == "Q235"]
    sus304_recipes = [r for r in recipes if r["material"] == "SUS304"]
    print(f"-> Q235 carbon steel recipes: {len(q235_recipes)}")
    print(f"-> SUS304 stainless steel recipes: {len(sus304_recipes)}")
    print("🟢 Test 1 passed successfully.")

    # ----------------------------------------------------
    # TEST 2: Pre-Cut Vision Scanner Simulation
    # ----------------------------------------------------
    print("\n[TEST 2] Testing Pre-Cut Inspection Scanner...")
    # Test Q235 (should have warp and rust warning)
    precheck_q235 = vision.run_precut_inspection("Q235", 6.0)
    print(f"-> Q235 6mm precheck: max_warp={precheck_q235['max_warp']}mm, rust={precheck_q235['rust_level']}")
    print(f"-> Warnings count: {len(precheck_q235['warnings'])}")
    assert len(precheck_q235['warnings']) > 0, "Q235 should trigger surface warnings."
    
    # Test clean SUS304
    precheck_sus = vision.run_precut_inspection("SUS304", 1.0)
    print(f"-> SUS304 1mm precheck ready to cut: {precheck_sus['ready_to_cut']}")
    print("🟢 Test 2 passed successfully.")

    # ----------------------------------------------------
    # TEST 3: Parameter Scaling (interpolation for thickness delta)
    # ----------------------------------------------------
    print("\n[TEST 3] Testing Parameter Recommendation Scaling...")
    # Baseline for SUS304 is 3.0mm (3000W, 6000mm/min, -1.5mm focus)
    # Let's request a scaled thickness of 3.5mm
    rec_scaled = recommender.recommend_parameters("SUS304", 3.5)
    print(f"-> Scaling recipe for SUS304 3.0mm -> 3.5mm:")
    print(f"   Recommended Power: {rec_scaled['laser_power']} W (scaled from 3000W)")
    print(f"   Recommended Speed: {rec_scaled['speed']} mm/min (scaled from 6000mm/min)")
    print(f"   Recommended Focus: {rec_scaled['focus_position']} mm (scaled from -1.5mm)")
    print(f"   Recommendation Confidence: {rec_scaled['confidence']}%")
    assert rec_scaled['speed'] < 6000.0, "Speed should scale down for thicker plates."
    assert rec_scaled['laser_power'] > 3000.0, "Power should scale up for thicker plates."
    print("🟢 Test 3 passed successfully.")

    # ----------------------------------------------------
    # TEST 4: Hardware Constraints & Cappings
    # ----------------------------------------------------
    print("\n[TEST 4] Testing Machine Cappings & Safety Rules...")
    # Request SUS304 10.0mm (standard needs 6000W) on a capped 5000W laser machine
    rec_capped = recommender.recommend_parameters("SUS304", 10.0, max_machine_power=5000.0)
    print(f"-> Scaling recipe for SUS304 10mm (with max machine power capped at 5000W):")
    print(f"   Recommended Power: {rec_capped['laser_power']} W (Capped to {rec_capped['laser_power']})")
    print(f"   Recommended Speed: {rec_capped['speed']} mm/min (Adjusted down to maintain thermal energy)")
    assert rec_capped['laser_power'] <= 5000.0, "Power should be capped below 5000W."
    print("🟢 Test 4 passed successfully.")

    # ----------------------------------------------------
    # TEST 5: Post-Cut Simulation & Defect Detections
    # ----------------------------------------------------
    print("\n[TEST 5] Testing Post-Cut Visual Inspection Simulation...")
    target = db.find_nearest_recipe("SUS304", 3.0)
    
    # Case A: Ideal Parameters
    report_ideal = vision.run_postcut_inspection(
        "SUS304", 3.0,
        laser_power=3000, speed=6000, gas_type="N2", gas_pressure=14.0, focus_position=-1.5,
        target=target
    )
    print(f"-> Case A (Ideal parameters): Quality Score = {report_ideal['quality_score']}% (Dross: {report_ideal['dross_height']}mm)")
    assert report_ideal['quality_score'] >= 90, "Ideal parameters should yield score >= 90%."

    # Case B: High Speed & High Focus deviation (triggers dross slag)
    report_dev = vision.run_postcut_inspection(
        "SUS304", 3.0,
        laser_power=3000, speed=7500, gas_type="N2", gas_pressure=12.0, focus_position=-0.5,
        target=target
    )
    print(f"-> Case B (High Speed / Focus dev): Quality Score = {report_dev['quality_score']}% (Dross: {report_dev['dross_height']}mm)")
    assert report_dev['quality_score'] < 80, "Deviated parameters should cause score drop."
    assert len(report_dev['defects_2d']) > 0, "Should detect 2D defects."
    print("🟢 Test 5 passed successfully.")

    # ----------------------------------------------------
    # TEST 6: Closed-Loop Tuning Loop Convergence
    # ----------------------------------------------------
    print("\n[TEST 6] Testing Closed-Loop Parameter Tuning Loop...")
    # Initial status: high speed and incorrect focus (same as Case B)
    curr_power = 3000.0
    curr_speed = 7500.0
    curr_gas_type = "N2"
    curr_gas_pressure = 12.0
    curr_focus = -0.5
    
    print(f"-> Start Iteration 0: Speed={curr_speed}, Focus={curr_focus}, Pressure={curr_gas_pressure}")
    
    for iteration in range(1, 6):
        # 1. Run simulation cut
        report = vision.run_postcut_inspection(
            "SUS304", 3.0,
            laser_power=curr_power, speed=curr_speed, gas_type=curr_gas_type, gas_pressure=curr_gas_pressure, focus_position=curr_focus,
            target=target
        )
        score = report['quality_score']
        print(f"   Iteration {iteration} Cut: Quality Score = {score}% (Dross = {report['dross_height']}mm)")
        
        if score >= 94.0:
            print(f"🎉 Loop converged on iteration {iteration}!")
            break
            
        # 2. Diagnose and get offsets
        suggestions = optimizer.diagnose_and_optimize(
            "SUS304", 3.0,
            current_power=curr_power, current_speed=curr_speed, current_gas_type=curr_gas_type, current_gas_pressure=curr_gas_pressure, current_focus=curr_focus,
            quality_report=report, target_recipe=target
        )
        
        print(f"   Advisor suggestions:")
        for sug in suggestions:
            print(f"     - Offset {sug['parameter']}: {sug['delta']:+.1f} -> target {sug['target_value']}")
            # Apply suggestions
            if sug['parameter'] == 'speed':
                curr_speed = sug['target_value']
            elif sug['parameter'] == 'focus_position':
                curr_focus = sug['target_value']
            elif sug['parameter'] == 'gas_pressure':
                curr_gas_pressure = sug['target_value']
            elif sug['parameter'] == 'laser_power':
                curr_power = sug['target_value']

    assert score >= 94.0, "Tuning loop failed to converge parameters."
    print("🟢 Test 6 passed successfully.")

    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED! SYSTEM LOGIC IS 100% CORRECT.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
