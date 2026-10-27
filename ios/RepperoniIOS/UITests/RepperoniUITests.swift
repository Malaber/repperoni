import XCTest

final class RepperoniUITests: XCTestCase {
  @MainActor
  func testWorkoutPersistsAndFeedsStatistics() throws {
    continueAfterFailure = false
    let url = try XCTUnwrap(
      Bundle(for: Self.self).url(forResource: "Fixture", withExtension: "json"))
    let fixture = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: String])
    let app = XCUIApplication()
    app.launchEnvironment["REPPERONI_TEST_TOKEN"] = fixture["token"]
    app.launchEnvironment["REPPERONI_TEST_SERVER"] = fixture["server"]
    app.launch()
    XCTAssertTrue(app.buttons["Start workout"].waitForExistence(timeout: 20))
    app.buttons["Start workout"].tap()
    XCTAssertTrue(app.buttons["Add exercise"].waitForExistence(timeout: 15))
    app.buttons["Add exercise"].tap()
    let search = app.searchFields.firstMatch
    XCTAssertTrue(search.waitForExistence(timeout: 10))
    search.tap()
    search.typeText("Bench")
    let exercise = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", "Bench Press"))
      .firstMatch
    XCTAssertTrue(exercise.waitForExistence(timeout: 10))
    exercise.tap()
    let log = app.buttons["Log set"]
    XCTAssertTrue(log.waitForExistence(timeout: 10))
    log.tap()
    XCTAssertTrue(app.staticTexts["Set 1 · 20.00 kg × 8"].waitForExistence(timeout: 15))
    app.terminate()
    app.launch()
    XCTAssertTrue(app.staticTexts["Set 1 · 20.00 kg × 8"].waitForExistence(timeout: 15))
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.lifetime = .keepAlways
    add(screenshot)
    app.swipeUp()
    app.buttons["Finish workout"].tap()
    app.buttons["Finish and save"].tap()
    XCTAssertTrue(app.buttons["Start workout"].waitForExistence(timeout: 15))
    // iPad uses a floating tab control outside XCUIElementTypeTabBar.
    app.buttons["Progress"].firstMatch.tap()
    XCTAssertTrue(app.staticTexts["Sets served"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["Bench Press"].exists)
    let progress = XCTAttachment(screenshot: app.screenshot())
    progress.lifetime = .keepAlways
    add(progress)
  }
}
